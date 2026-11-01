"""S2: degraded P2P call with unrelated TURN overload."""

from calldiag.config import CALLER, TURN_SERVER
from calldiag.models import CallTelemetry
from calldiag.scenarios.builder import Plateau, Profile
from calldiag.scenarios.common import build_media_scenario, new_builder, qos_profiles

QOS_PLATEAUS = {"rtt_ms": (60, 85, 280, 12), "jitter_ms": (60, 85, 40, 4), "packet_loss_pct": (60, 85, 8, 1), "bitrate_kbps": (61, 86, 800, 60)}
TURN_CPU = (38.0, 3.0)
TURN_CPU_PLATEAU = (55, 90, 90, 2, 3, 4)
LOGS = (
    (56.0, TURN_SERVER, "WARN", "turn", False, "CPU load high: 88% (threshold 85%)"),
    (61.0, CALLER, "WARN", "media", True, "inbound video packet loss 8.2% over last 1s"),
    (62.5, CALLER, "WARN", "ice", True, "candidate-pair RTT 276 ms (srflx↔srflx)"),
    (64.0, CALLER, "WARN", "media", True, "NACK burst: 30 NACKs in 1s (inbound video)"),
    (88.0, CALLER, "INFO", "media", True, "bandwidth estimate recovered to 1450 kbps"),
    (92.0, TURN_SERVER, "INFO", "turn", False, "CPU load normal: 41%"),
)


def build() -> CallTelemetry:
    return build_media_scenario(
        new_builder("S2"), mode="p2p", qos=qos_profiles(plateaus=QOS_PLATEAUS),
        turn_cpu=Profile(*TURN_CPU, plateaus=(Plateau(*TURN_CPU_PLATEAU),)),
        logs=LOGS,
    )
