"""Evaluation targets kept separate from telemetry generation."""

from dataclasses import dataclass

from calldiag.models import PHASE_ORDER


@dataclass(frozen=True)
class ExpectedOutcome:
    phase_status: dict[str, str]
    has_incident: bool
    qos_interval_offset: tuple[float, float] | None
    primary_rule: str
    primary_confidence: str
    severity: str
    required_inferences: tuple[str, ...] = ()
    required_hypotheses: tuple[str, ...] = ()
    required_rejected: tuple[str, ...] = ()
    forbidden_inferences: tuple[str, ...] = ()
    required_missing_metrics: tuple[str, ...] = ()


def _statuses(*statuses: str) -> dict[str, str]:
    return dict(zip((phase.value for phase in PHASE_ORDER), statuses, strict=True))


EXPECTED_OUTCOMES: dict[str, ExpectedOutcome] = {
    "S0": ExpectedOutcome(
        _statuses("ok", "ok", "ok", "ok", "ok"), False, None, "HEALTHY_CALL", "High", "none",
        required_inferences=("HEALTHY_CALL",),
        forbidden_inferences=("TURN_OVERLOAD_DEGRADATION", "NETWORK_PATH_DEGRADATION"),
    ),
    "S1": ExpectedOutcome(
        _statuses("ok", "ok", "ok", "degraded", "ok"), True, (80, 102), "TURN_OVERLOAD_DEGRADATION", "High", "major",
        required_inferences=("TURN_OVERLOAD_DEGRADATION", "NETWORK_PATH_DEGRADATION"),
    ),
    "S2": ExpectedOutcome(
        _statuses("ok", "ok", "ok", "degraded", "ok"), True, (60, 85), "NETWORK_PATH_DEGRADATION", "High", "major",
        required_rejected=("TURN_OVERLOAD_DEGRADATION",),
        forbidden_inferences=("TURN_OVERLOAD_DEGRADATION",),
    ),
    "S3": ExpectedOutcome(
        _statuses("ok", "ok", "failed", "skipped", "ok"), True, None, "ICE_CONNECTIVITY_FAILURE", "High", "critical",
        forbidden_inferences=("NETWORK_PATH_DEGRADATION", "TURN_OVERLOAD_DEGRADATION", "HEALTHY_CALL"),
    ),
    "S4": ExpectedOutcome(
        _statuses("ok", "ok", "ok", "ok", "ok"), False, None, "RELAY_NOT_A_FAULT", "High", "none",
        required_inferences=("RELAY_NOT_A_FAULT", "HEALTHY_CALL"),
        forbidden_inferences=("TURN_OVERLOAD_DEGRADATION", "NETWORK_PATH_DEGRADATION"),
    ),
    "S5": ExpectedOutcome(
        _statuses("ok", "failed", "skipped", "skipped", "ok"), True, None, "SIGNALING_FAILURE", "High", "critical",
        forbidden_inferences=("ICE_CONNECTIVITY_FAILURE", "NETWORK_PATH_DEGRADATION", "TURN_OVERLOAD_DEGRADATION"),
    ),
    "S6": ExpectedOutcome(
        _statuses("ok", "ok", "ok", "degraded", "ok"), True, (80, 102), "NETWORK_PATH_DEGRADATION", "Medium", "major",
        required_hypotheses=("TURN_OVERLOAD_DEGRADATION",),
        forbidden_inferences=("TURN_OVERLOAD_DEGRADATION",),
        required_missing_metrics=("turn-01/turn_cpu_pct",),
    ),
}
