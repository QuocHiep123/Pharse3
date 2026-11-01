"""Shared constants, metric metadata and pipeline rules."""

from datetime import UTC, datetime
from typing import Literal, TypedDict

BASE_START = datetime(2026, 10, 31, 10, 20, 0, tzinfo=UTC)
CALLER, CALLEE, SIGNALING, TURN_SERVER = "alice", "bob", "signaling", "turn-01"
CLOCK_MODEL = "single_synthetic_clock"
SAMPLE_INTERVAL_SEC = 1
MILLISECONDS_PER_SECOND = 1000
SAMPLE_DECIMALS = 1
PERCENT_MAX = 100.0
DEFAULT_RAMP_IN_SEC = 2.0
DEFAULT_RAMP_OUT_SEC = 3.0
DEFAULT_SCENARIO_DIR = "data/scenarios"
CANDIDATE_TYPES = frozenset({"host", "srflx", "relay"})
END_REASONS = frozenset({"normal", "ice_failed", "signaling_timeout", "rejected", "dtls_failed"})
MEDIA_KINDS = frozenset({"audio", "video"})


class MetricMeta(TypedDict):
    label: str
    unit: str
    category: Literal["qos", "resource"]
    worse: Literal["higher", "lower"]
    source: str
    direction: Literal["none", "inbound"]
    decimals: int


METRIC_META: dict[str, MetricMeta] = {
    "rtt_ms": {"label": "RTT", "unit": "ms", "category": "qos", "worse": "higher", "source": CALLER, "direction": "none", "decimals": 0},
    "jitter_ms": {"label": "Jitter", "unit": "ms", "category": "qos", "worse": "higher", "source": CALLER, "direction": "inbound", "decimals": 0},
    "packet_loss_pct": {"label": "Packet loss", "unit": "%", "category": "qos", "worse": "higher", "source": CALLER, "direction": "inbound", "decimals": 1},
    "bitrate_kbps": {"label": "Inbound bitrate", "unit": "kbps", "category": "qos", "worse": "lower", "source": CALLER, "direction": "inbound", "decimals": 0},
    "turn_cpu_pct": {"label": "TURN CPU", "unit": "%", "category": "resource", "worse": "higher", "source": TURN_SERVER, "direction": "none", "decimals": 0},
    "client_cpu_pct": {"label": "Client CPU", "unit": "%", "category": "resource", "worse": "higher", "source": CALLER, "direction": "none", "decimals": 0},
}

BASELINE_SEC = 20
BASELINE_MIN_SAMPLES = 10
ROLLING_WINDOW = 5
ROLLING_MIN_PERIODS = 3
MIN_ANOMALY_SEC = 5
MERGE_GAP_SEC = 3
INCIDENT_MERGE_GAP_SEC = 5
RESOURCE_OVERLAP_SEC = 10
MISSING_RATIO_THRESHOLD = 0.5
METRIC_RULES = {
    "rtt_ms": {"abs": 250.0, "rel": 2.0},
    "jitter_ms": {"abs": 30.0, "rel": 2.5},
    "packet_loss_pct": {"abs": 5.0, "rel": 3.0},
    "bitrate_kbps": {"abs": 900.0, "rel": 0.6},
    "turn_cpu_pct": {"abs": 85.0, "rel": 1.5},
    "client_cpu_pct": {"abs": 85.0, "rel": 1.5},
}
CORRELATION_PRE_SEC = 10
CORRELATION_POST_SEC = 10
PHASE_FAILURE_POST_SEC = 5
LOG_LEVEL_WEIGHT = {"DEBUG": 0, "INFO": 1, "WARN": 2, "ERROR": 3}
RELATED_LOG_MIN_SCORE = 2
MAX_LOG_FACTS = 6
BANNED_FACT_WORDS = [
    "gây ra", "nguyên nhân", "có khả năng", "do lỗi", "bởi vì",
    "caused", "because", "due to", "likely", "probably",
]
PRECEDENCE_TOLERANCE_SEC = 5
MAX_NEXT_CHECKS = 6
MAJOR_INCIDENT_MIN_SEC = 20
MAJOR_LOSS_PCT = 10.0
EVAL_INTERVAL_TOLERANCE_SEC = 5


class PhaseEventRule(TypedDict):
    start: str
    success: str
    failures: tuple[str, ...]


# Enum values are strings here to keep config independent of models.
PHASE_EVENT_RULES: dict[str, PhaseEventRule] = {
    "call_setup": {
        "start": "CALL_CREATED", "success": "CALL_ACCEPTED",
        "failures": ("CALL_REJECTED",),
    },
    "offer_answer": {
        "start": "OFFER_CREATED", "success": "SET_REMOTE_DESCRIPTION_OK",
        "failures": ("SIGNALING_TIMEOUT", "SET_REMOTE_DESCRIPTION_FAILED"),
    },
    "ice": {
        "start": "ICE_GATHERING_START", "success": "ICE_CONNECTED",
        "failures": ("ICE_FAILED",),
    },
    "media": {
        "start": "DTLS_CONNECTING", "success": "FIRST_RTP_RECEIVED",
        "failures": ("DTLS_FAILED",),
    },
}
TRACE_METRIC_EVENTS: dict[str, tuple[str, tuple[str, ...]]] = {
    "time_to_accept_ms": ("CALL_CREATED", ("CALL_ACCEPTED",)),
    "time_to_answer_ms": ("OFFER_SENT", ("ANSWER_RECEIVED",)),
    "ice_gathering_ms": ("ICE_GATHERING_START", ("ICE_GATHERING_COMPLETE",)),
    "ice_checking_ms": ("ICE_CHECKING", ("ICE_CONNECTED", "ICE_FAILED")),
    "dtls_ms": ("DTLS_CONNECTING", ("DTLS_CONNECTED",)),
    "time_to_first_media_ms": ("CALL_CREATED", ("FIRST_RTP_RECEIVED",)),
    "call_duration_ms": ("CALL_CREATED", ("CALL_ENDED",)),
}
TIMELINE_MIN_LOG_LEVEL = "INFO"
TIMELINE_KIND_ORDER = {"event": 0, "anomaly_start": 1, "log": 2, "anomaly_end": 3}
OTEL_PHASE_STATUS = {
    "ok": "OK", "degraded": "OK", "failed": "ERROR",
    "skipped": "UNSET", "incomplete": "UNSET",
}

# Anomaly/summary statistics are rounded so report JSON carries no float noise.
STAT_DECIMALS = 2
SUMMARY_P95_QUANTILE = 0.95
ANOMALY_CATEGORY_ORDER = {"qos": 0, "resource": 1}
CORRELATION_MIN_LOG_LEVEL = "INFO"
CORRELATION_WARNING_LEVEL = "WARN"
CORRELATION_ON_PATH_BONUS = 1
CORRELATION_CATEGORY_BONUS = 1
CORRELATION_OTHER_CALL_PENALTY = 2
INCIDENT_LOG_CATEGORIES = frozenset({"media", "ice", "turn"})
PHASE_FAILURE_LOG_CATEGORIES = {
    "call_setup": frozenset({"signaling"}),
    "offer_answer": frozenset({"signaling"}),
    "ice": frozenset({"ice", "turn"}),
    "media": frozenset({"dtls", "media"}),
}

DEFAULT_OUTPUT_DIR = "out"
CONFIDENCE_LEVELS = ("Low", "Medium", "High")
CONFIDENCE_ORDER = {"High": 0, "Medium": 1, "Low": 2}
MULTI_QOS_MIN_METRICS = 2
ENGINEERING_MAX_QOS_FACTS = 3
# Order in which QoS FACTs are picked for the engineering summary.
QOS_SUMMARY_PRIORITY = ("rtt_ms", "packet_loss_pct", "jitter_ms", "bitrate_kbps")
ENGINEERING_MAX_UNKNOWNS = 2
SUMMARY_SMALL_NUMBER_LIMIT = 5
RULE_SPECIFICITY = {
    "SIGNALING_FAILURE": 5, "ICE_CONNECTIVITY_FAILURE": 5,
    "TURN_OVERLOAD_DEGRADATION": 3, "NETWORK_PATH_DEGRADATION": 1,
    "RELAY_NOT_A_FAULT": 2, "HEALTHY_CALL": 1,
}
REPORT_HEADLINES = {
    "SIGNALING_FAILURE": "Cuộc gọi thất bại ở phase Offer/Answer SDP: không nhận được answer",
    "ICE_CONNECTIVITY_FAILURE": "Cuộc gọi thất bại ở phase ICE: không tìm được network path",
    "TURN_OVERLOAD_DEGRADATION": "Chất lượng suy giảm {window}, có khả năng liên quan tới quá tải TURN server",
    "NETWORK_PATH_DEGRADATION": "Chất lượng suy giảm {window} trên media path",
    "RELAY_NOT_A_FAULT": "Không có incident: cuộc gọi đi qua TURN relay và chất lượng bình thường",
    "HEALTHY_CALL": "Không có incident",
}
PHASE_STATUS_ICONS = {"ok": "✅", "degraded": "🟡", "failed": "❌", "skipped": "⏭️", "incomplete": "⚠️"}

# LLM summary (plan 10, M7). Provider and model come from the environment, never hard-coded.
LLM_PROVIDERS = ("openai",)
LLM_DEFAULT_PROVIDER = "openai"
LLM_TIMEOUT_SEC = 30.0
LLM_MAX_RETRIES = 1
LLM_CACHE_DIR = "out/llm_cache"
LLM_PROMPT_VERSION = "1"            # bump when the prompt changes so old cache entries stop matching
EXEC_SUMMARY_MAX_WORDS = 80
