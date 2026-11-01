"""S6: degraded relay call whose TURN CPU collector sends no values."""

from calldiag.models import CallTelemetry
from calldiag.scenarios import data, s1_turn_overload
from calldiag.scenarios.builder import Profile
from calldiag.scenarios.common import build_media_scenario, new_builder, qos_profiles

MISSING_TURN_SOURCE = "turn-01/turn_cpu_pct: collector không gửi dữ liệu"


def build() -> CallTelemetry:
    return build_media_scenario(
        new_builder("S6"), mode="relay", qos=qos_profiles(plateaus=s1_turn_overload.QOS_PLATEAUS),
        turn_cpu=Profile(0.0, 0.0, missing=True),
        logs=s1_turn_overload.DEGRADED_MEDIA_LOGS,
        missing_sources=[*data.MISSING_SOURCES, MISSING_TURN_SOURCE],
    )
