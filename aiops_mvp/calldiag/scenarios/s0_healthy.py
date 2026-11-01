"""S0: healthy direct P2P call."""

from calldiag.models import CallTelemetry
from calldiag.scenarios.builder import Profile
from calldiag.scenarios.common import build_media_scenario, new_builder, qos_profiles

TURN_CPU = (38.0, 3.0)


def build() -> CallTelemetry:
    return build_media_scenario(
        new_builder("S0"), mode="p2p", qos=qos_profiles(),
        turn_cpu=Profile(*TURN_CPU),
    )
