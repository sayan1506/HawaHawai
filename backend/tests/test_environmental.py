import json
import os
import socket
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from environmental.config import coordinates, school_profile
from environmental.http import ProviderError, fetch_json, request_once
from environmental.providers import OpenMeteoProvider, IndianObservationProvider
from environmental.cache import MemoryCache, CacheError, DynamoCache, encode_payload, decode_payload
from environmental.service import EnvironmentalService, cache_prefix
from app import handler

NOW = 1791441000


def fixture():
    times = [NOW // 3600 * 3600 + i * 3600 for i in range(72)]
    return {"latitude": 28.6, "longitude": 77.2, "utc_offset_seconds": 0, "hourly_units": {"time": "unixtime", "pm2_5": "μg/m³", "pm10": "μg/m³", "us_aqi": "USAQI"}, "current_units": {"time": "unixtime", "pm2_5": "μg/m³", "pm10": "μg/m³", "us_aqi": "USAQI"}, "current": {"time": NOW - 300, "pm2_5": 45, "pm10": 80, "us_aqi": 120}, "hourly": {"time": times, "pm2_5": [45] * 72, "pm10": [80] * 72, "us_aqi": [120] * 72}}


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.school = school_profile()
        self.provider = OpenMeteoProvider(lambda url: fixture())

    def test_valid_response_and_provenance(self):
        data = self.provider.fetch(self.school, NOW)
        point = data["current"]["point"]
        self.assertEqual(point["aqi"][0]["scale"], "US_AQI")
        self.assertEqual(point["pollutants"][0]["unit"], "ug/m3")
        self.assertEqual(point["pollutants"][0]["original_unit"], "μg/m³")
        self.assertIsNone(point["pollutants"][0]["observed_at"])
        self.assertEqual(point["pollutants"][0]["source_type"], "model_forecast")
        self.assertTrue(point["valid_at"].endswith("+00:00"))
        self.assertIsNone(data["forecast"]["generated_at"])
        self.assertIsNone(data["current"]["sources"][0]["location"]["station_id"])

    def test_invalid_coordinates(self):
        for lat, lon in [(91, 77), (28, 181), ("28", 77), (True, 77), (float("nan"), 77), (None, 77)]:
            with self.subTest(lat=lat), self.assertRaises(ValueError):
                coordinates(lat, lon)

    def test_invalid_school_configuration(self):
        for lat in (0, None, "bad"):
            school = {**self.school, "latitude": lat}
            with patch.dict(os.environ, {"HAWAHAWAI_SCHOOL_PROFILE_JSON": json.dumps(school)}), self.assertRaises(ValueError):
                school_profile()

    def test_missing_schema(self):
        for change in ({"hourly": {}}, {"utc_offset_seconds": 19800}, {"latitude": None}, {"hourly_units": {}}):
            with self.subTest(change=change), self.assertRaises(ProviderError):
                self.provider.normalize({**fixture(), **change}, self.school, NOW)

    def test_partial_and_unsupported_units(self):
        raw = fixture()
        raw["hourly_units"]["pm10"] = "ppm"
        raw["current"]["pm2_5"] = None
        data = self.provider.normalize(raw, self.school, NOW)
        self.assertTrue(any("UNSUPPORTED_UNIT" in w for w in data["forecast"]["warnings"]))
        self.assertEqual([p["name"] for p in data["forecast"]["points"][0]["pollutants"]], ["pm2_5"])
        self.assertEqual([p["name"] for p in data["current"]["point"]["pollutants"]], ["pm10"])

    def test_null_readings_never_fabricated(self):
        raw = fixture()
        for var in ("pm2_5", "pm10"):
            raw["hourly"][var] = [None] * 72
        with self.assertRaises(ProviderError):
            self.provider.normalize(raw, self.school, NOW)

    def test_array_mismatch_and_bad_timestamps(self):
        for field, value in [("pm10", [1]), ("time", ["yesterday"] * 72), ("time", [NOW] * 72)]:
            raw = fixture()
            raw["hourly"][field] = value
            with self.assertRaises(ProviderError):
                self.provider.normalize(raw, self.school, NOW)

    def test_official_adapter_never_invents_readings(self):
        self.assertEqual(IndianObservationProvider().fetch(self.school, NOW)["observations"], [])

    def test_timeout_and_connection_bounded_retries(self):
        for error in (socket.timeout(), ConnectionError()):
            request, sleep = Mock(side_effect=error), Mock()
            with self.assertRaises(ProviderError):
                fetch_json("https://example.invalid", request, sleep)
            self.assertEqual(request.call_count, 2)
            self.assertEqual(sleep.call_count, 1)

    def test_transient_retry_success(self):
        request = Mock(side_effect=[ProviderError("UPSTREAM_TRANSIENT"), fixture()])
        self.assertEqual(fetch_json("x", request, Mock()), fixture())
        self.assertEqual(request.call_count, 2)

    def test_rate_limit_no_retry(self):
        request = Mock(side_effect=ProviderError("RATE_LIMITED", 120))
        with self.assertRaises(ProviderError) as caught:
            fetch_json("x", request, Mock())
        self.assertEqual(request.call_count, 1)
        self.assertEqual(caught.exception.retry_after, 120)

    def test_malformed_json(self):
        response = Mock(status=200)
        response.read.return_value = b"not json"
        connection = Mock()
        connection.getresponse.return_value = response
        with patch("environmental.http.http.client.HTTPSConnection", return_value=connection), self.assertRaises(ProviderError) as caught:
            request_once("https://air-quality-api.open-meteo.com/v1/air-quality?x=1")
        self.assertEqual(caught.exception.code, "MALFORMED_JSON")
        connection.close.assert_called_once()


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.school, self.cache, self.now = school_profile(), MemoryCache(), NOW
        self.provider = Mock()
        self.provider.fetch.side_effect = lambda school, now: OpenMeteoProvider().normalize(fixture(), school, now)
        self.service = EnvironmentalService(self.cache, self.provider, lambda: self.now)

    def test_cache_miss_hit_and_separate_entries(self):
        first = self.service.get(self.school, "current")
        second = self.service.get(self.school, "forecast")
        third = self.service.get(self.school, "current")
        self.assertEqual(first["cache"]["status"], "refreshed")
        self.assertEqual(second["cache"]["status"], "hit")
        self.assertEqual(third["cache"]["status"], "hit")
        self.assertEqual(self.provider.fetch.call_count, 1)
        self.assertEqual(len(second["points"]), 48)

    def test_stale_timeout_fallback_and_negative_cache(self):
        first = self.service.get(self.school, "current")
        self.now += 901
        self.provider.fetch.side_effect = ProviderError("TIMEOUT")
        result = self.service.get(self.school, "current")
        self.assertEqual(result["status"], "stale")
        self.assertEqual(result["retrieved_at"], first["retrieved_at"])
        self.assertEqual(result["pollutants"], first["pollutants"])
        self.assertIn("LIVE_REFRESH_FAILED: TIMEOUT", result["warnings"])
        self.service.get(self.school, "current")
        self.assertEqual(self.provider.fetch.call_count, 2)

    def test_rate_limit_fallback_and_cooldown(self):
        self.service.get(self.school, "forecast")
        self.now += 3601
        self.provider.fetch.side_effect = ProviderError("RATE_LIMITED", 120)
        result = self.service.get(self.school, "forecast")
        self.assertEqual(result["status"], "stale")
        self.assertIn("LIVE_REFRESH_FAILED: RATE_LIMITED", result["warnings"])
        self.service.get(self.school, "forecast")
        self.assertEqual(self.provider.fetch.call_count, 2)

    def test_expired_ttl_not_fresh_and_unavailable(self):
        self.service.get(self.school, "forecast")
        self.now += 21601
        self.provider.fetch.side_effect = ProviderError("TIMEOUT")
        result = self.service.get(self.school, "forecast")
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["points"], [])

    def test_missing_data_with_failure(self):
        self.provider.fetch.side_effect = ProviderError("CONNECTION_FAILED")
        result = self.service.get(self.school, "current")
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["pollutants"], [])
        self.assertEqual(result["observations"], [])

    def test_lock_prevents_stampede(self):
        self.cache.acquire(cache_prefix(self.school) + "#lock", self.now)
        result = self.service.get(self.school, "forecast")
        self.assertEqual(result["status"], "unavailable")
        self.provider.fetch.assert_not_called()

    def test_dynamo_operations_scoped(self):
        client = Mock()
        client.get_item.return_value = {"Item": {"payload": {"S": '{"data":1}'}}}
        cache = DynamoCache("hawahawai-test-cache", client)
        self.assertEqual(cache.get("a"), {"data": 1})
        cache.put("b", {"x": 2})
        self.assertIn("expires_at", client.put_item.call_args.kwargs["Item"])
        with self.assertRaises(CacheError):
            DynamoCache("ChugLi", client)

    def test_cache_failure_fails_closed(self):
        self.cache.get = Mock(side_effect=CacheError())
        with self.assertRaises(CacheError):
            self.service.get(self.school, "current")
        self.provider.fetch.assert_not_called()

    def test_compressed_payload_and_old_entry_compatibility(self):
        data = {"data": fixture(), "fetched_at": NOW, "fresh_until": NOW + 900}
        encoded = encode_payload(data)
        self.assertEqual(decode_payload(encoded), data)
        self.assertLess(len(encoded), len(json.dumps(data)))
        self.assertEqual(decode_payload(json.dumps(data)), data)
        client = Mock()
        client.get_item.return_value = {"Item": {"payload": {"S": encoded}}}
        self.assertEqual(DynamoCache("hawahawai-test-cache", client).get("a"), data)

    def test_corrupt_cache_fails_closed(self):
        client = Mock()
        client.get_item.return_value = {"Item": {"payload": {"S": "gzip:corrupt!"}}}
        with self.assertRaises(CacheError):
            DynamoCache("hawahawai-test-cache", client).get("a")

    def test_local_cors(self):
        from local_server import RequestHandler
        server = RequestHandler.__new__(RequestHandler)
        server.send_header = Mock()
        server.headers = {"Origin": "http://127.0.0.1:5173"}
        server.cors()
        server.send_header.assert_any_call("Access-Control-Allow-Origin", "http://127.0.0.1:5173")
        server.send_header.reset_mock()
        server.headers = {"Origin": "https://untrusted.invalid"}
        server.cors()
        server.send_header.assert_not_called()

    def test_dynamo_lock_aliases_reserved_owner(self):
        client = Mock()
        cache = DynamoCache("hawahawai-test-cache", client)
        token = cache.acquire("lock", NOW)
        request = client.update_item.call_args.kwargs
        self.assertEqual(request["ExpressionAttributeNames"], {"#owner": "owner"})
        self.assertIn("#owner", request["UpdateExpression"])
        cache.release("lock", token)
        self.assertEqual(client.update_item.call_args.kwargs["ConditionExpression"], "#owner=:owner")

    def test_http_429_preserves_retry_after(self):
        response = Mock(status=429)
        response.getheader.return_value = "120"
        connection = Mock()
        connection.getresponse.return_value = response
        with patch("environmental.http.http.client.HTTPSConnection", return_value=connection), self.assertRaises(ProviderError) as caught:
            request_once("https://air-quality-api.open-meteo.com/v1/air-quality?x=1")
        self.assertEqual(caught.exception.code, "RATE_LIMITED")
        self.assertEqual(caught.exception.retry_after, 120)

    def test_api_and_schema(self):
        document = json.loads((ROOT / "contracts/openapi.json").read_text())
        for suffix, schema in [("air", "AirReading"), ("forecast", "Forecast")]:
            with patch("environmental.service.get_service", return_value=self.service):
                response = handler({"rawPath": f'/v1/schools/{self.school["school_id"]}/{suffix}'}, None)
            self.assertEqual(response["statusCode"], 200)
            Draft202012Validator({**document, "$ref": f"#/components/schemas/{schema}"}, format_checker=FormatChecker()).validate(json.loads(response["body"]))

    def test_api_invalid_and_missing(self):
        for params in ({"latitude": "91", "longitude": "77"}, {"latitude": "28"}, {"latitude": "nan", "longitude": "77"}, {"latitude": "bad", "longitude": "77"}, {"force": "true"}):
            result = handler({"rawPath": f'/v1/schools/{self.school["school_id"]}/air', "queryStringParameters": params}, None)
            self.assertEqual(result["statusCode"], 400)
        self.provider.fetch.side_effect = ProviderError("TIMEOUT")
        with patch("environmental.service.get_service", return_value=self.service):
            result = handler({"rawPath": f'/v1/schools/{self.school["school_id"]}/air'}, None)
        self.assertEqual(result["statusCode"], 503)


if __name__ == "__main__":
    unittest.main()
