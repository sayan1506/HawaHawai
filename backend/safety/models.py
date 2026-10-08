"""Explicit, immutable policy inputs. Validation never supplies missing evidence."""
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import math
from urllib.parse import urlsplit


class Decision(str, Enum):
    GO_OUTDOORS = "GO_OUTDOORS"
    MODIFIED_OUTDOORS = "MODIFIED_OUTDOORS"
    INDOOR_ONLY = "INDOOR_ONLY"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"


class VerificationState(str, Enum):
    VERIFIED_ACTIVE = "VERIFIED_ACTIVE"
    VERIFIED_INACTIVE = "VERIFIED_INACTIVE"
    UNKNOWN = "UNKNOWN"
    STALE = "STALE"
    CONFLICTING = "CONFLICTING"


def instant(value):
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Timezone-aware timestamp required")
    return parsed.astimezone(timezone.utc)


def number(value):
    return isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def official_url(value):
    parsed = urlsplit(value)
    if parsed.scheme != "https" or parsed.hostname not in {
        "caqm.nic.in", "www.caqm.nic.in", "edudel.nic.in", "www.edudel.nic.in",
        "edustud.nic.in", "www.edustud.nic.in", "www.pib.gov.in", "pib.gov.in",
        "www.dpcc.delhigovt.nic.in", "dpcc.delhigovt.nic.in",
    } or parsed.username or parsed.password or parsed.port not in (None, 443) or parsed.fragment:
        raise ValueError("Official HTTPS document URL required")
    return value


@dataclass(frozen=True)
class ActivityContext:
    jurisdiction: str = "NCT_DELHI"
    grade: int | None = None
    activity: str = "all"

    def __post_init__(self):
        if self.jurisdiction != "NCT_DELHI":
            raise ValueError("Only the configured Delhi pilot jurisdiction is supported")
        if self.grade is not None and (type(self.grade) is not int or not 0 <= self.grade <= 12):
            raise ValueError("Grade must be 0 (pre-primary) to 12")
        if self.activity not in {"all", "assembly", "sports", "physical_education", "other", "indoor"}:
            raise ValueError("Unsupported activity")


@dataclass(frozen=True)
class Policy:
    version: str = "school-safety-v1"
    # EPA/AirNow US-AQI category boundaries; NOT Indian AQI/GRAP thresholds.
    modify_above: int = 100
    vigorous_indoor_above: int = 150
    indoor_above: int = 200
    observation_max_age_seconds: int = 900
    model_max_age_seconds: int = 900
    forecast_retrieval_max_age_seconds: int = 3600
    activity_window_hours: int = 3

    def __post_init__(self):
        if not self.version or (self.modify_above, self.vigorous_indoor_above, self.indoor_above) != (100, 150, 200):
            raise ValueError("Only documented US-AQI category boundaries are supported")
        if (self.observation_max_age_seconds, self.model_max_age_seconds,
            self.forecast_retrieval_max_age_seconds, self.activity_window_hours) != (900, 900, 3600, 3):
            raise ValueError("Unsupported evidence-validity policy")


POLICY_SOURCES = (
    {"evidence_id": "epa-school-guidance-2014", "title": "Air Quality and Outdoor Activity Guidance for Schools",
     "url": "https://document.airnow.gov/air-quality-and-outdoor-guidance-for-schools.pdf", "authority": "US EPA / CDC", "published_on": "2014-08", "scope": "US AQI health guidance; project-adopted precaution, not Indian law"},
    {"evidence_id": "epa-us-aqi-categories", "title": "AQI Basics", "url": "https://www.airnow.gov/aqi/aqi-basics/",
     "authority": "US EPA / AirNow", "published_on": None, "scope": "US AQI category boundaries only; no scale conversion"},
)
