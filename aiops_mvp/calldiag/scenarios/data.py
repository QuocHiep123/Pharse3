"""Shared scenario timeline segments and baselines (plan 02).

Kept out of calldiag.config so pipeline modules never see scenario-keyed data.
Parameters specific to one scenario live in that scenario's module.
"""

from calldiag.config import CALLEE, CALLER, METRIC_META, SIGNALING, TURN_SERVER

MEDIA_END_T = 120.2
ICE_FAILURE_END_T = 33.0
SIGNALING_TIMEOUT_END_T = 11.8
QOS_FROM_T, QOS_TO_T = 5, 119
NORMAL_HANGUP_T, TERMINATION_DELAY_SEC = 120.0, 0.2
MEDIA_SNAPSHOT_INTERVAL_SEC = 10
TURN_REFRESH_INTERVAL_SEC = 15
OTHER_CALL_LOG_MIN_END_T, OTHER_CALL_LOG_T = 30, 30.5
OTHER_CALL_ID = "call-0999"
MISSING_SOURCES = ("bob/getStats: không thu thập trong MVP",)
EXPECTED_METRICS_MEDIA = tuple(f"{m['source']}/{name}" for name, m in METRIC_META.items() if m["category"] == "qos") + (
    f"{CALLER}/client_cpu_pct", f"{TURN_SERVER}/turn_cpu_pct",
)
EXPECTED_METRICS_RESOURCE = (f"{CALLER}/client_cpu_pct", f"{TURN_SERVER}/turn_cpu_pct")
BASE_QOS = {"rtt_ms": (80.0, 4.0), "jitter_ms": (10.0, 1.5), "packet_loss_pct": (0.4, 0.15), "bitrate_kbps": (1500.0, 60.0)}
CLIENT_CPU = (30.0, 3.0)
SCENARIO_SEEDS = {f"S{i}": 1000 + i for i in range(7)}
SCENARIO_CALL_IDS = {sid: f"call-{seed}" for sid, seed in SCENARIO_SEEDS.items()}
SCENARIO_TITLES = {
    "S0": "Healthy P2P", "S1": "TURN overload", "S2": "Network degradation trên P2P",
    "S3": "ICE failure", "S4": "Relay nhưng healthy", "S5": "Signaling timeout",
    "S6": "Relay degraded, thiếu metric TURN",
}

# Each event is (offset, component, EventType name, attrs).
SETUP_EVENTS = (
    (0.000, SIGNALING, "CALL_CREATED", {}),
    (0.050, SIGNALING, "INVITE_SENT", {}),
    (0.120, CALLEE, "INVITE_RECEIVED", {}),
    (1.500, CALLEE, "CALL_ACCEPTED", {}),
)
OFFER_ANSWER_EVENTS = (
    (1.600, CALLER, "OFFER_CREATED", {}), (1.650, CALLER, "OFFER_SENT", {}),
    (1.750, CALLEE, "OFFER_RECEIVED", {}), (1.850, CALLEE, "ANSWER_CREATED", {}),
    (1.900, CALLEE, "ANSWER_SENT", {}), (2.000, CALLER, "ANSWER_RECEIVED", {}),
    (2.050, CALLER, "SET_REMOTE_DESCRIPTION_OK", {}),
)
TIMEOUT_EVENTS = OFFER_ANSWER_EVENTS[:2] + (
    (11.650, CALLER, "SIGNALING_TIMEOUT", {"waited_ms": 10000}),
    (11.700, CALLER, "HANGUP", {"by": CALLER, "reason": "signaling_timeout"}),
    (11.800, SIGNALING, "CALL_ENDED", {"reason": "signaling_timeout"}),
)
ICE_GATHERING_EVENTS = (
    (2.100, CALLER, "ICE_GATHERING_START", {}),
    (2.150, CALLER, "ICE_CANDIDATE_GATHERED", {"candidate_type": "host", "address": "10.0.0.12:50000"}),
    (2.300, CALLER, "ICE_CANDIDATE_GATHERED", {"candidate_type": "srflx", "address": "198.51.100.7:61000"}),
    (2.600, CALLER, "ICE_CANDIDATE_GATHERED", {"candidate_type": "relay", "address": "203.0.113.10:49152"}),
    (2.650, CALLER, "ICE_GATHERING_COMPLETE", {}), (2.700, CALLER, "ICE_CHECKING", {}),
)
ICE_PAIR_CHECKS = {
    "p2p": ((2.900, "host", "host", False), (3.100, "srflx", "srflx", True)),
    "relay": ((2.900, "host", "host", False), (3.300, "srflx", "srflx", False), (3.600, "relay", "srflx", True)),
    "fail": ((3.000, "host", "host", False), (3.600, "srflx", "srflx", False), (5.000, "relay", "srflx", False)),
}
ICE_CONNECTED_T = {"p2p": 3.200, "relay": 3.700}
ICE_SELECTED_T = {"p2p": 3.150, "relay": 3.650}
ICE_FAILURE_EVENTS = (
    (32.700, CALLER, "ICE_FAILED", {"after_ms": 30000}),
    (32.800, CALLER, "HANGUP", {"by": CALLER, "reason": "ice_failed"}),
    (33.000, SIGNALING, "CALL_ENDED", {"reason": "ice_failed"}),
)
MEDIA_EVENTS = (
    (0.200, CALLER, "DTLS_CONNECTING", {}), (0.400, CALLER, "DTLS_CONNECTED", {}),
    (0.600, CALLER, "FIRST_RTP_SENT", {}),
    (0.700, CALLER, "FIRST_RTP_RECEIVED", {"ssrc": 1234567, "kind": "video"}),
)
# Logs are (offset, component, level, category, call_scoped, message).
SETUP_LOGS = (
    (0.000, SIGNALING, "INFO", "signaling", True, "call created caller=alice callee=bob"),
    (1.500, SIGNALING, "INFO", "signaling", True, "bob accepted call"),
)
OFFER_ANSWER_LOGS = (
    (1.750, SIGNALING, "INFO", "signaling", True, "OFFER relayed alice→bob (SDP 2.9 KB, 2 m= sections)"),
    (2.000, SIGNALING, "INFO", "signaling", True, "ANSWER relayed bob→alice"),
)
TIMEOUT_LOGS = (
    (1.700, SIGNALING, "WARN", "signaling", True, "websocket for bob closed (code 1006); OFFER queued"),
    (11.650, CALLER, "ERROR", "signaling", True, "no ANSWER received within 10000 ms"),
    (11.800, SIGNALING, "INFO", "signaling", True, "call ended reason=signaling_timeout"),
)
TURN_ALLOCATION_LOG = (2.600, TURN_SERVER, "INFO", "turn", True, "allocation created relay=203.0.113.10:49152")
ICE_FAILURE_LOGS = (
    (32.700, CALLER, "ERROR", "ice", True, "ICE connection state failed after 30000 ms"),
    (33.000, SIGNALING, "INFO", "signaling", True, "call ended reason=ice_failed"),
)
MEDIA_LOGS = (
    (0.400, CALLER, "INFO", "dtls", True, "DTLS handshake complete (role client)"),
    (0.700, CALLER, "INFO", "media", True, "first inbound RTP ssrc=1234567 (video)"),
)
