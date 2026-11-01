"""S4: TURN relay usage without a fault."""

from calldiag.models import CallTelemetry
from calldiag.scenarios.builder import Profile
from calldiag.scenarios.common import build_media_scenario, new_builder, qos_profiles

RELAY_QOS = {"rtt_ms": (130.0, 6.0), "jitter_ms": (11.0, 1.5), "packet_loss_pct": (0.5, 0.15), "bitrate_kbps": (1450.0, 60.0)}
TURN_CPU = (45.0, 3.0)


def build() -> CallTelemetry:
    return build_media_scenario(
        new_builder("S4"), mode="relay", qos=qos_profiles(baseline=RELAY_QOS),
        turn_cpu=Profile(*TURN_CPU),
    )
