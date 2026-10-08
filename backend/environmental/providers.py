import math
from datetime import datetime, timezone
from typing import Protocol, TypedDict
from urllib.parse import urlencode
from .config import School, coordinates
from .http import ProviderError, fetch_json

SOURCE = "open-meteo-cams-global"
VARIABLES = {"pm2_5": "pm2_5", "pm10": "pm10", "carbon_monoxide": "co", "nitrogen_dioxide": "no2", "sulphur_dioxide": "so2", "ozone": "o3"}


def stamp(epoch):
    if isinstance(epoch, bool) or not isinstance(epoch, (float, int)) or not math.isfinite(epoch):
        raise ProviderError("INVALID_TIMESTAMP")
    try:
        return datetime.fromtimestamp(epoch, timezone.utc).isoformat()
    except (ValueError, OverflowError, OSError):
        raise ProviderError("INVALID_TIMESTAMP") from None


def number(value):
    return not isinstance(value, bool) and isinstance(value, (float, int)) and math.isfinite(value) and value >= 0


class ProviderBundle(TypedDict):
    current: dict
    forecast: dict


class EnvironmentalProvider(Protocol):
    def fetch(self, school: School, now: float) -> ProviderBundle: ...


class OpenMeteoProvider:
    def __init__(self, transport=fetch_json):
        self.transport = transport

    def fetch(self, school, now):
        coordinates(school["latitude"], school["longitude"])
        variables = ",".join([*VARIABLES, "us_aqi"])
        query = urlencode({"latitude": school["latitude"], "longitude": school["longitude"], "domains": "cams_global", "timezone": "GMT", "timeformat": "unixtime", "forecast_hours": 72, "hourly": variables, "current": variables})
        return self.normalize(self.transport("https://air-quality-api.open-meteo.com/v1/air-quality?" + query), school, now)

    def normalize(self, raw, school, now):
        if not isinstance(raw, dict) or raw.get("utc_offset_seconds") != 0:
            raise ProviderError("INVALID_SCHEMA")
        try:
            coordinates(raw.get("latitude"), raw.get("longitude"))
        except ValueError:
            raise ProviderError("INVALID_GRID_LOCATION") from None
        warnings = ["MODELED_NOT_STATION_OBSERVATIONS", "US_AQI_NOT_INDIAN_AQI", "CAMS_GLOBAL_APPROX_45_KM_GRID", "MODEL_RUN_TIMESTAMP_NOT_PROVIDED"]
        retrieved = stamp(now)
        source = {"source_id": SOURCE, "name": "Open-Meteo / Copernicus CAMS Global", "url": "https://open-meteo.com/en/docs/air-quality-api", "kind": "model_forecast", "observed_at": None, "retrieved_at": retrieved, "valid_until": None, "freshness": "fresh", "location": {"latitude": raw["latitude"], "longitude": raw["longitude"], "station_id": None, "distance_km": None}, "limitations": ["Modeled grid values, not physical station measurements.", "Approximately 45 km global grid; native 3-hour values interpolated hourly; local school exposure may differ.", "CAMS global forecast updates approximately every 12 hours. API retrieval time is not model initialization time.", "Attribution: Open-Meteo and Copernicus CAMS (https://ads.atmosphere.copernicus.eu/datasets/cams-global-atmospheric-composition-forecasts)."]}

        def values(block, units, when, index=None):
            if not isinstance(block, dict) or not isinstance(units, dict) or units.get("time") != "unixtime":
                raise ProviderError("INVALID_SCHEMA")
            pollutants, aqi = [], []
            for variable in [*VARIABLES, "us_aqi"]:
                value = block.get(variable)
                if index is not None:
                    if value is not None and (not isinstance(value, list) or len(value) != len(block["time"])):
                        raise ProviderError("INVALID_SCHEMA")
                    value = value[index] if isinstance(value, list) else None
                if value is None:
                    warnings.append("MISSING_" + variable.upper())
                    continue
                if not number(value):
                    warnings.append("INVALID_" + variable.upper())
                    continue
                expected = "USAQI" if variable == "us_aqi" else "μg/m³"
                if units.get(variable) != expected:
                    warnings.append("UNSUPPORTED_UNIT_" + variable.upper())
                    continue
                meta = {"source_id": SOURCE, "observed_at": None, "forecast_for": when, "source_type": "model_forecast"}
                if variable == "us_aqi":
                    aqi.append({**meta, "value": value, "scale": "US_AQI"})
                else:
                    pollutants.append({**meta, "name": VARIABLES[variable], "value": value, "unit": "ug/m3", "original_unit": units[variable], "averaging_period": "model instantaneous concentration"})
            return {"valid_at": when, "aqi": aqi, "pollutants": pollutants}

        hourly = raw.get("hourly")
        if not isinstance(hourly, dict) or not isinstance(hourly.get("time"), list) or not hourly["time"]:
            raise ProviderError("INVALID_SCHEMA")
        epochs = hourly["time"]
        if any(not isinstance(t, (int, float)) or isinstance(t, bool) for t in epochs):
            raise ProviderError("INVALID_TIMESTAMP")
        if any(b - a != 3600 for a, b in zip(epochs, epochs[1:])):
            raise ProviderError("INVALID_FORECAST_INTERVAL")
        points = [values(hourly, raw.get("hourly_units"), stamp(t), i) for i, t in enumerate(epochs)]
        if len([p for p in points if datetime.fromisoformat(p["valid_at"]).timestamp() >= now]) < 48 or not any(p["pollutants"] for p in points):
            raise ProviderError("INSUFFICIENT_FORECAST")
        current = raw.get("current")
        current_point = None
        if isinstance(current, dict) and current.get("time") is not None:
            current_point = values(current, raw.get("current_units"), stamp(current["time"]))
            if not current_point["pollutants"]:
                current_point = None
        else:
            warnings.append("MODELED_CURRENT_MISSING")
        common = {"sources": [source], "warnings": sorted(set(warnings)), "retrieved_at": retrieved, "data_quality": "modeled_grid_estimate"}
        return {"current": {**common, "point": current_point}, "forecast": {**common, "points": points, "generated_at": None}}


class IndianObservationProvider:
    """Fail-closed adapter until credentials, station metadata and units are verified."""
    def fetch(self, school, now):
        return {"observations": [], "status": "unavailable", "source_name": "CPCB / data.gov.in", "source_type": "measurement", "source_url": "https://www.data.gov.in/catalog/real-time-air-quality-index", "retrieved_at": stamp(now), "warnings": ["OFFICIAL_OBSERVATIONS_UNAVAILABLE: authenticated access and pollutant semantics not verified; no official Indian AQI available."]}


class OpenAQObservationProvider:
    def fetch(self, school, now):
        return {"observations": [], "status": "unavailable", "source_name": "OpenAQ", "source_type": "measurement", "source_url": "https://docs.openaq.org/", "retrieved_at": stamp(now), "warnings": ["OPENAQ_NOT_INTEGRATED: API key and Delhi-NCR station coverage not verified."]}
