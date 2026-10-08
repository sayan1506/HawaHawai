"""Bounded public provider probes: one Open-Meteo request and two unauthenticated checks."""
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def main():
    school = json.loads((ROOT / "contracts/demo-school.json").read_text())
    params = {"latitude": school["latitude"], "longitude": school["longitude"], "domains": "cams_global", "timezone": "GMT", "timeformat": "unixtime", "forecast_hours": 72,
              "hourly": "pm2_5,pm10,carbon_monoxide,nitrogen_dioxide,sulphur_dioxide,ozone,us_aqi", "current": "pm2_5,pm10,carbon_monoxide,nitrogen_dioxide,sulphur_dioxide,ozone,us_aqi"}
    evidence = {"checked_at": datetime.now(timezone.utc).isoformat(), "school": school}
    targets = [
        ("open_meteo", "https://air-quality-api.open-meteo.com/v1/air-quality?" + urlencode(params)),
        ("data_gov_in_no_key", "https://api.data.gov.in/resource/3b01bcb8-0b14-4abf-b6f2-c1bfd384ba69?format=json&limit=1"),
        ("openaq_no_key", "https://api.openaq.org/v3/locations?" + urlencode({"coordinates": f'{school["latitude"]},{school["longitude"]}', "radius": 25000, "limit": 1})),
    ]
    for name, url in targets:
        try:
            with urlopen(url, timeout=15) as response:
                body = json.load(response)
                evidence[name] = {"http_status": response.status, "body": body if name == "open_meteo" else {"keys": list(body) if isinstance(body, dict) else []}}
        except HTTPError as error:
            evidence[name] = {"http_status": error.code}
        except (URLError, TimeoutError, ValueError) as error:
            evidence[name] = {"error_type": type(error).__name__}
    target = ROOT / ".local/phase1-provider-probe.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    for name, result in evidence.items():
        if name in {"checked_at", "school"}:
            continue
        summary = {k: v for k, v in result.items() if k != "body"}
        if name == "open_meteo" and "body" in result:
            body = result["body"]
            summary.update({"timezone": body.get("timezone"), "hours": len(body.get("hourly", {}).get("time", [])), "units": body.get("hourly_units"), "current_time": body.get("current", {}).get("time"), "grid_location": [body.get("latitude"), body.get("longitude")]})
        print(name, json.dumps(summary))


if __name__ == "__main__":
    main()
