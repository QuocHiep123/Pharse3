"""Independent telemetry fixture and shared M3 scenario results."""

from dataclasses import dataclass
import os

import pytest

# Tests must not pick up the developer's real aiops_mvp/.env (API keys, model).
os.environ["CALLDIAG_ENV_FILE"] = ""

from calldiag import config
from calldiag.models import (
    AnomalyResult, CallMeta, CallTelemetry, Direction, EvidenceBundle, EventType, LogCategory, LogLevel,
    LogRecord, MetricName, MetricSample, PathContext, Phase, PhaseSpan, PipelineResult, TraceEvent, TraceMetrics,
)
from calldiag.pipeline.anomaly import detect_anomalies
from calldiag.pipeline.correlate import build_path_context, correlate
from calldiag.pipeline.facts import FactStore, extract_facts
from calldiag.pipeline.phases import compute_trace_metrics, extract_selected_path, localize_phases, mark_degraded
from calldiag.pipeline.run import run_scenario
from calldiag.scenarios import REGISTRY
from calldiag.scenarios import build_all
from calldiag.utils import at


@pytest.fixture
def bundle() -> CallTelemetry:
    return CallTelemetry(
        meta=CallMeta(
            call_id="call-1000", scenario_id="S0", title="Test telemetry",
            start_ts=config.BASE_START, end_ts=at(config.BASE_START, 2),
            expected_metrics=["alice/rtt_ms"],
        ),
        events=[TraceEvent(
            event_id="ev-001", ts=config.BASE_START, call_id="call-1000",
            phase=Phase.CALL_SETUP, component=config.SIGNALING, type=EventType.CALL_CREATED,
        ), TraceEvent(
            event_id="ev-002", ts=at(config.BASE_START, 1), call_id="call-1000",
            phase=Phase.ICE, component=config.CALLER, type=EventType.ICE_SELECTED_PAIR,
            attrs={"local_type": "srflx", "remote_type": "srflx", "via_turn": False, "turn_server": None},
        )],
        metrics=[MetricSample(
            sample_id="m-alice-rtt_ms-0001", ts=at(config.BASE_START, 1),
            call_id="call-1000", source=config.CALLER, direction=Direction.NONE,
            metric=MetricName.RTT_MS, value=None,
        )],
        logs=[LogRecord(
            log_id="log-001", ts=config.BASE_START, call_id=None, component=config.TURN_SERVER,
            level=LogLevel.INFO, category=LogCategory.TURN, message="server ready",
        ), LogRecord(
            log_id="log-002", ts=at(config.BASE_START, 1), call_id="call-1000", component=config.CALLER,
            level=LogLevel.INFO, category=LogCategory.ICE, message="selected candidate pair srflx↔srflx",
        )],
    )


@dataclass
class M3Result:
    bundle: CallTelemetry
    phases: list[PhaseSpan]
    trace: TraceMetrics
    path: PathContext
    anomalies: AnomalyResult
    evidence: list[EvidenceBundle]
    facts: FactStore


@pytest.fixture(scope="session")
def m3_results() -> dict[str, M3Result]:
    results: dict[str, M3Result] = {}
    for sid, telemetry in build_all().items():
        phases = localize_phases(telemetry)
        selected = extract_selected_path(telemetry)
        trace = compute_trace_metrics(telemetry, phases, selected)
        anomalies = detect_anomalies(telemetry, phases)
        phases = mark_degraded(phases, anomalies)
        path = build_path_context(telemetry, selected)
        evidence = correlate(telemetry, phases, anomalies, path)
        facts = extract_facts(telemetry, phases, trace, path, anomalies, evidence)
        results[sid] = M3Result(telemetry, phases, trace, path, anomalies, evidence, facts)
    return results


@pytest.fixture(scope="session")
def results() -> dict[str, PipelineResult]:
    return {sid: run_scenario(sid) for sid in REGISTRY}
