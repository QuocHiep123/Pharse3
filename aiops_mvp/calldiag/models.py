"""Telemetry contract and shared enums (plan 01)."""

from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, Field, field_validator

from calldiag import config


class Phase(str, Enum):
    CALL_SETUP = "call_setup"
    OFFER_ANSWER = "offer_answer"
    ICE = "ice"
    MEDIA = "media"
    TERMINATION = "termination"


PHASE_ORDER: list[Phase] = list(Phase)
PHASE_LABELS: dict[Phase, str] = dict(zip(PHASE_ORDER, (
    "Call Setup", "Offer/Answer SDP", "ICE Candidate Exchange",
    "Media Established", "Call Termination",
), strict=True))


class EventType(str, Enum):
    CALL_CREATED = "CALL_CREATED"
    INVITE_SENT = "INVITE_SENT"
    INVITE_RECEIVED = "INVITE_RECEIVED"
    CALL_ACCEPTED = "CALL_ACCEPTED"
    CALL_REJECTED = "CALL_REJECTED"
    OFFER_CREATED = "OFFER_CREATED"
    OFFER_SENT = "OFFER_SENT"
    OFFER_RECEIVED = "OFFER_RECEIVED"
    ANSWER_CREATED = "ANSWER_CREATED"
    ANSWER_SENT = "ANSWER_SENT"
    ANSWER_RECEIVED = "ANSWER_RECEIVED"
    SET_REMOTE_DESCRIPTION_OK = "SET_REMOTE_DESCRIPTION_OK"
    SET_REMOTE_DESCRIPTION_FAILED = "SET_REMOTE_DESCRIPTION_FAILED"
    SIGNALING_TIMEOUT = "SIGNALING_TIMEOUT"
    ICE_GATHERING_START = "ICE_GATHERING_START"
    ICE_CANDIDATE_GATHERED = "ICE_CANDIDATE_GATHERED"
    ICE_GATHERING_COMPLETE = "ICE_GATHERING_COMPLETE"
    ICE_CHECKING = "ICE_CHECKING"
    ICE_PAIR_SUCCEEDED = "ICE_PAIR_SUCCEEDED"
    ICE_PAIR_FAILED = "ICE_PAIR_FAILED"
    ICE_SELECTED_PAIR = "ICE_SELECTED_PAIR"
    ICE_CONNECTED = "ICE_CONNECTED"
    ICE_FAILED = "ICE_FAILED"
    DTLS_CONNECTING = "DTLS_CONNECTING"
    DTLS_CONNECTED = "DTLS_CONNECTED"
    DTLS_FAILED = "DTLS_FAILED"
    FIRST_RTP_SENT = "FIRST_RTP_SENT"
    FIRST_RTP_RECEIVED = "FIRST_RTP_RECEIVED"
    HANGUP = "HANGUP"
    CALL_ENDED = "CALL_ENDED"


EVENT_PHASE: dict[EventType, Phase] = {
    event: phase
    for phase, events in (
        (Phase.CALL_SETUP, (EventType.CALL_CREATED, EventType.INVITE_SENT, EventType.INVITE_RECEIVED, EventType.CALL_ACCEPTED, EventType.CALL_REJECTED)),
        (Phase.OFFER_ANSWER, (EventType.OFFER_CREATED, EventType.OFFER_SENT, EventType.OFFER_RECEIVED, EventType.ANSWER_CREATED, EventType.ANSWER_SENT, EventType.ANSWER_RECEIVED, EventType.SET_REMOTE_DESCRIPTION_OK, EventType.SET_REMOTE_DESCRIPTION_FAILED, EventType.SIGNALING_TIMEOUT)),
        (Phase.ICE, (EventType.ICE_GATHERING_START, EventType.ICE_CANDIDATE_GATHERED, EventType.ICE_GATHERING_COMPLETE, EventType.ICE_CHECKING, EventType.ICE_PAIR_SUCCEEDED, EventType.ICE_PAIR_FAILED, EventType.ICE_SELECTED_PAIR, EventType.ICE_CONNECTED, EventType.ICE_FAILED)),
        (Phase.MEDIA, (EventType.DTLS_CONNECTING, EventType.DTLS_CONNECTED, EventType.DTLS_FAILED, EventType.FIRST_RTP_SENT, EventType.FIRST_RTP_RECEIVED)),
        (Phase.TERMINATION, (EventType.HANGUP, EventType.CALL_ENDED)),
    )
    for event in events
}


class Direction(str, Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"
    NONE = "none"


class MetricName(str, Enum):
    RTT_MS = "rtt_ms"
    JITTER_MS = "jitter_ms"
    PACKET_LOSS_PCT = "packet_loss_pct"
    BITRATE_KBPS = "bitrate_kbps"
    TURN_CPU_PCT = "turn_cpu_pct"
    CLIENT_CPU_PCT = "client_cpu_pct"


class MetricCategory(str, Enum):
    QOS = "qos"
    RESOURCE = "resource"


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"


class LogCategory(str, Enum):
    SIGNALING = "signaling"
    ICE = "ice"
    TURN = "turn"
    DTLS = "dtls"
    MEDIA = "media"
    SYSTEM = "system"


class Confidence(str, Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class Severity(str, Enum):
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"
    NONE = "none"


class _UTCModel(BaseModel):
    @field_validator(
        "ts", "start_ts", "end_ts", "established_ts", "peak_ts",
        "window_start", "window_end", "focus_start", "focus_end", "generated_at",
        "incident_window_start", "incident_window_end", check_fields=False,
    )
    @classmethod
    def normalize_utc(cls, value: datetime | None) -> datetime | None:
        return value.astimezone(UTC) if value is not None else None


class CallMeta(_UTCModel):
    call_id: str
    scenario_id: str
    title: str
    start_ts: AwareDatetime
    end_ts: AwareDatetime
    caller: str = config.CALLER
    callee: str = config.CALLEE
    measured_endpoint: str = config.CALLER
    turn_server: str = config.TURN_SERVER
    clock_model: str = config.CLOCK_MODEL
    expected_metrics: list[str]
    missing_sources: list[str] = Field(default_factory=list)


class TraceEvent(_UTCModel):
    event_id: str
    ts: AwareDatetime
    call_id: str
    phase: Phase
    component: str
    type: EventType
    attrs: dict[str, Any] = Field(default_factory=dict)


class MetricSample(_UTCModel):
    sample_id: str
    ts: AwareDatetime
    call_id: str | None
    source: str
    direction: Direction
    metric: MetricName
    value: float | None = Field(allow_inf_nan=False)


class LogRecord(_UTCModel):
    log_id: str
    ts: AwareDatetime
    call_id: str | None
    component: str
    level: LogLevel
    category: LogCategory
    message: str
    attrs: dict[str, Any] = Field(default_factory=dict)


class CallTelemetry(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    meta: CallMeta
    events: list[TraceEvent]
    metrics: list[MetricSample]
    logs: list[LogRecord]


class PhaseStatus(str, Enum):
    OK = "ok"
    FAILED = "failed"
    DEGRADED = "degraded"
    SKIPPED = "skipped"
    INCOMPLETE = "incomplete"


class TimelineItem(_UTCModel):
    ts: AwareDatetime
    kind: Literal["event", "log", "anomaly_start", "anomaly_end"]
    ref_id: str
    phase: Phase | None
    component: str
    summary: str


class PhaseSpan(_UTCModel):
    phase: Phase
    label: str
    status: PhaseStatus
    start_ts: AwareDatetime | None
    end_ts: AwareDatetime | None
    duration_ms: int | None
    # Media only: FIRST_RTP_RECEIVED time. A typed field (not attrs) so it survives JSON.
    established_ts: AwareDatetime | None = None
    start_event_id: str | None
    end_event_id: str | None
    event_ids: list[str]
    failure_event_id: str | None = None
    attrs: dict[str, Any] = Field(default_factory=dict)
    degraded_interval_ids: list[str] = Field(default_factory=list)


class SelectedPath(_UTCModel):
    event_id: str
    ts: AwareDatetime
    local_type: str
    remote_type: str
    via_turn: bool
    turn_server: str | None


class TraceMetrics(BaseModel):
    time_to_accept_ms: int | None
    time_to_answer_ms: int | None
    ice_gathering_ms: int | None
    ice_checking_ms: int | None
    dtls_ms: int | None
    time_to_first_media_ms: int | None
    call_duration_ms: int | None
    candidate_counts: dict[str, int]
    pair_results: list[dict[str, Any]]
    selected_pair: SelectedPath | None
    end_reason: str | None


class Baseline(_UTCModel):
    source: str
    direction: Direction
    metric: MetricName
    available: bool
    median: float | None
    mad: float | None
    window_start: AwareDatetime | None
    window_end: AwareDatetime | None
    n_samples: int


class MetricAnomaly(_UTCModel):
    anomaly_id: str
    source: str
    direction: Direction
    metric: MetricName
    category: MetricCategory
    start_ts: AwareDatetime
    end_ts: AwareDatetime
    duration_sec: float
    baseline_value: float | None
    median_value: float
    peak_value: float
    peak_ts: AwareDatetime
    threshold_abs: float
    threshold_rel_value: float | None
    first_sample_id: str
    peak_sample_id: str
    last_sample_id: str
    sample_ids: list[str]
    interval_ids: list[str] = Field(default_factory=list)


class IncidentInterval(_UTCModel):
    interval_id: str
    start_ts: AwareDatetime
    end_ts: AwareDatetime
    duration_sec: float
    qos_anomaly_ids: list[str]
    resource_anomaly_ids: list[str]


class MetricSummary(_UTCModel):
    source: str
    direction: Direction
    metric: MetricName
    scope: Literal["media_phase", "interval"]
    interval_id: str | None
    window_start: AwareDatetime
    window_end: AwareDatetime
    n: int
    n_missing: int
    missing_ratio: float
    median: float | None
    p95: float | None
    min: float | None
    max: float | None
    first_sample_id: str | None
    last_sample_id: str | None


class MissingMetric(_UTCModel):
    source: str
    metric: MetricName
    missing_ratio: float
    window_start: AwareDatetime
    window_end: AwareDatetime
    sample_ids: list[str]


class AnomalyResult(BaseModel):
    skipped: bool
    skip_reason: str | None = None
    baselines: list[Baseline] = Field(default_factory=list)
    anomalies: list[MetricAnomaly] = Field(default_factory=list)
    incidents: list[IncidentInterval] = Field(default_factory=list)
    summaries: list[MetricSummary] = Field(default_factory=list)
    missing: list[MissingMetric] = Field(default_factory=list)


class PathContext(BaseModel):
    selected: SelectedPath | None
    via_turn: bool | None
    media_components: list[str]
    control_components: list[str]
    relay_candidate_gathered: bool
    description: str


class CorrelatedLog(_UTCModel):
    log_id: str
    ts: AwareDatetime
    component: str
    level: LogLevel
    category: LogCategory
    message: str
    same_call: bool | None
    on_path: bool
    lag_sec: float
    score: int


class EvidenceFocus(str, Enum):
    INCIDENT_INTERVAL = "incident_interval"
    PHASE_FAILURE = "phase_failure"
    NONE = "none"


class EvidenceBundle(_UTCModel):
    evidence_id: str
    call_id: str
    focus: EvidenceFocus
    focus_ref: str | None
    focus_start: AwareDatetime
    focus_end: AwareDatetime
    window_start: AwareDatetime
    window_end: AwareDatetime
    path: PathContext
    related_logs: list[CorrelatedLog]
    resource_anomaly_ids: list[str]
    clock_alignment: str
    missing_evidence: list[str]


class FactKind(str, Enum):
    PHASE_STATUS = "phase_status"
    SELECTED_PATH = "selected_path"
    ICE_CHECKS = "ice_checks"
    TRACE_TIMING = "trace_timing"
    METRIC_CHANGE = "metric_change"
    METRIC_LEVEL = "metric_level"
    MISSING_DATA = "missing_data"
    LOG_EVENT = "log_event"


class Fact(_UTCModel):
    fact_id: str
    kind: FactKind
    statement: str
    ts: AwareDatetime | None = None
    window_start: AwareDatetime | None = None
    window_end: AwareDatetime | None = None
    source: str | None = None
    metric: MetricName | None = None
    direction: Direction | None = None
    value_before: float | None = None
    value_after: float | None = None
    value_peak: float | None = None
    unit: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    refs: list[str]


class CondState(str, Enum):
    TRUE = "true"
    FALSE = "false"
    UNKNOWN = "unknown"


class ConditionResult(BaseModel):
    name: str
    description: str
    state: CondState
    fact_ids: list[str]
    note: str | None = None


class CounterEvidence(BaseModel):
    description: str
    fact_ids: list[str]


class Inference(BaseModel):
    inference_id: str
    rule_id: str
    conclusion: str
    supported_by: list[str]
    confidence: Confidence
    confidence_reasons: list[str]
    counter_evidence: list[CounterEvidence]
    alternatives: list[str]
    conditions: list[ConditionResult]
    specificity: int
    focus_ref: str | None


class Hypothesis(BaseModel):
    hypothesis_id: str
    rule_id: str
    statement: str
    supporting_fact_ids: list[str]
    missing_evidence: list[str]
    how_to_verify: list[str]


class RejectedHypothesis(BaseModel):
    rejected_id: str
    rule_id: str
    statement: str
    contradicting_fact_ids: list[str]
    reason: str


class ReasoningResult(BaseModel):
    inferences: list[Inference]
    hypotheses: list[Hypothesis]
    rejected: list[RejectedHypothesis]
    primary_inference_id: str | None
    unknowns: list[str]
    next_checks: list[str]


class ValidationIssue(BaseModel):
    level: Literal["error", "warning"]
    code: str
    message: str
    ref: str | None = None


class ValidationResult(BaseModel):
    passed: bool
    issues: list[ValidationIssue]


class ReportSummary(_UTCModel):
    headline: str
    has_incident: bool
    failed_phase: Phase | None
    incident_window_start: AwareDatetime | None
    incident_window_end: AwareDatetime | None
    severity: Severity
    primary_inference_id: str | None
    primary_rule_id: str | None
    confidence: Confidence | None


class ReportScope(BaseModel):
    call_id: str
    participants: list[str]
    measured_endpoint: str
    direction: str
    path: str


class IncidentReport(_UTCModel):
    report_version: Literal["1.0"] = "1.0"
    generated_at: AwareDatetime
    scenario_id: str
    summary: ReportSummary
    scope: ReportScope
    phases: list[PhaseSpan]
    trace_metrics: TraceMetrics
    incident_intervals: list[IncidentInterval]
    timeline: list[TimelineItem]
    facts: list[Fact]
    related_logs: list[CorrelatedLog]
    inferences: list[Inference]
    hypotheses: list[Hypothesis]
    rejected: list[RejectedHypothesis]
    unknowns: list[str]
    next_checks: list[str]
    evidence: list[EvidenceBundle]
    engineering_summary: str
    executive_summary: str
    summary_source: Literal["template", "llm"] = "template"
    validation: ValidationResult | None = None


class PipelineResult(BaseModel):
    bundle: CallTelemetry
    phases: list[PhaseSpan]
    path: PathContext
    anomalies: AnomalyResult
    evidence: list[EvidenceBundle]
    report: IncidentReport
