import json
import math
import os
from pathlib import Path
from typing import TypedDict


class School(TypedDict):
    school_id: str
    name: str
    latitude: float
    longitude: float
    timezone: str


def coordinates(latitude, longitude):
    for value, low, high in ((latitude, -90, 90), (longitude, -180, 180)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError("Invalid coordinates")


def school_profile() -> School:
    raw = os.environ.get("HAWAHAWAI_SCHOOL_PROFILE_JSON")
    school = json.loads(raw) if raw else json.loads((Path(__file__).resolve().parents[2] / "contracts/demo-school.json").read_text())
    coordinates(school.get("latitude"), school.get("longitude"))
    if not (27.8 <= school["latitude"] <= 29.5 and 76.5 <= school["longitude"] <= 78):
        raise ValueError("School must be in the configured Delhi-NCR pilot area")
    if not school.get("school_id") or not school.get("name", "").strip() or school.get("timezone") != "Asia/Kolkata":
        raise ValueError("Invalid school configuration")
    return school
