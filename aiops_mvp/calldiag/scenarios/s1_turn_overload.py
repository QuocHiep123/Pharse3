"""S1: relay call with TURN resource and QoS degradation."""

from calldiag.config import CALLER, TURN_SERVER
from calldiag.models import CallTelemetry
from calldiag.scenarios.builder import Plateau, Profile
from calldiag.scenarios.common import build_media_scenario, new_builder, qos_profiles

# Plateaus are (t_start, t_end, mean, std[, ramp_in, ramp_out]); S6 reuses the QoS part.
QOS_PLATEAUS = {"rtt_ms": (80, 102, 310, 12), "jitter_ms": (80, 102, 45, 4), "packet_loss_pct": (80, 102, 12, 1.2), "bitrate_kbps": (81, 103, 600, 50)}
TURN_CPU = (40.0, 3.0)
TURN_CPU_PLATEAU = (74, 104, 95, 1.5, 3, 4)
# Logs are (offset, component, level, category, call_scoped, message).
DEGRADED_MEDIA_LOGS = (
    (81.0, CALLER, "WARN", "media", True, "inbound video packet loss 11.8% over last 1s"),
    (83.0, CALLER, "WARN", "media", True, "NACK burst: 48 NACKs in 1s (inbound video)"),
    (90.0, CALLER, "INFO", "media", True, "bandwidth estimate decreased to 620 kbps"),
)
TURN_OVERLOAD_LOGS = DEGRADED_MEDIA_LOGS + (
    (74.0, TURN_SERVER, "WARN", "turn", False, "CPU load high: 94% (threshold 85%)"),
    (76.5, TURN_SERVER, "WARN", "turn", True, "allocation refresh latency 450 ms"),
    (86.0, TURN_SERVER, "ERROR", "turn", False, "relay send queue overflow: dropped 132 packets"),
    (106.0, TURN_SERVER, "INFO", "turn", False, "CPU load normal: 44%"),
)


def build() -> CallTelemetry:
    return build_media_scenario(
        new_builder("S1"), mode="relay", qos=qos_profiles(plateaus=QOS_PLATEAUS),
        turn_cpu=Profile(*TURN_CPU, plateaus=(Plateau(*TURN_CPU_PLATEAU),)),
        logs=TURN_OVERLOAD_LOGS,
    )
