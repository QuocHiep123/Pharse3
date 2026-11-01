from datetime import timedelta

import pytest

from calldiag import config
from calldiag.models import EvidenceBundle, EvidenceFocus, LogCategory, LogLevel, Phase
from calldiag.pipeline.correlate import build_path_context, correlate
from calldiag.pipeline.phases import extract_selected_path
from calldiag.scenarios import REGISTRY
from calldiag.utils import at
from conftest import M3Result


@pytest.mark.parametrize(("sid", "focus", "description"), [
    ("S0", EvidenceFocus.NONE, "srflx↔srflx (trực tiếp)"),
    ("S1", EvidenceFocus.INCIDENT_INTERVAL, "relay↔srflx qua turn-01"),
    ("S2", EvidenceFocus.INCIDENT_INTERVAL, "srflx↔srflx (trực tiếp)"),
    ("S3", EvidenceFocus.PHASE_FAILURE, "chưa có selected pair"),
    ("S4", EvidenceFocus.NONE, "relay↔srflx qua turn-01"),
    ("S5", EvidenceFocus.PHASE_FAILURE, "chưa có selected pair"),
    ("S6", EvidenceFocus.INCIDENT_INTERVAL, "relay↔srflx qua turn-01"),
])
def test_evidence_table(sid: str, focus: EvidenceFocus, description: str, m3_results: dict[str, M3Result]) -> None:
    result = m3_results[sid]
    assert len(result.evidence) == 1
    item = result.evidence[0]
    assert item.evidence_id == "eb-01"
    assert item.call_id == result.bundle.meta.call_id
    assert item.focus == focus
    assert item.path.description == description
    assert item.clock_alignment
    assert [(-log.score, log.ts, log.log_id) for log in item.related_logs] == sorted((-log.score, log.ts, log.log_id) for log in item.related_logs)
    assert not any(log.level == LogLevel.DEBUG or log.message == "allocation created for another call" for log in item.related_logs)
    assert all(item.window_start <= log.ts <= item.window_end for log in item.related_logs)
    if sid in {"S0", "S4"}:
        assert item.related_logs == []
        media = next(p for p in result.phases if p.phase == Phase.MEDIA)
        assert item.focus_start == item.window_start == media.established_ts
        assert item.focus_end == item.window_end == media.end_ts
    elif focus == EvidenceFocus.INCIDENT_INTERVAL:
        assert item.focus_ref == "inc-01"
        assert item.window_start == item.focus_start - timedelta(seconds=config.CORRELATION_PRE_SEC)
        assert item.window_end == item.focus_end + timedelta(seconds=config.CORRELATION_POST_SEC)
    else:
        assert item.focus_ref == ("ice" if sid == "S3" else "offer_answer")
        assert item.window_start == item.focus_start
        assert item.window_end == item.focus_end + timedelta(seconds=config.PHASE_FAILURE_POST_SEC)


def test_path_components_separate_control_and_media(m3_results: dict[str, M3Result]) -> None:
    p2p, relay, failed, signaling = (m3_results[sid].path for sid in ("S2", "S1", "S3", "S5"))
    assert p2p.media_components == ["alice", "bob"]
    assert relay.media_components == ["alice", "turn-01", "bob"]
    assert p2p.control_components == ["alice", "bob", "signaling", "turn-01"]
    assert failed.media_components == [] and failed.via_turn is None
    assert failed.relay_candidate_gathered is True
    assert signaling.control_components == ["alice", "bob", "signaling"]
    assert signaling.relay_candidate_gathered is False


def test_s1_turn_log_is_on_path_and_precedes_incident(m3_results: dict[str, M3Result]) -> None:
    logs = m3_results["S1"].evidence[0].related_logs
    cpu = next(log for log in logs if "CPU load high" in log.message)
    assert cpu.on_path is True and cpu.lag_sec < 0 and cpu.same_call is None
    refresh = next(log for log in logs if "refresh latency" in log.message)
    assert refresh.same_call is True
    assert any(log.level == LogLevel.ERROR and log.component == "turn-01" for log in logs)
    assert any("bandwidth estimate decreased" in log.message for log in logs)


def test_s2_turn_logs_remain_visible_as_off_path(m3_results: dict[str, M3Result]) -> None:
    turn = [log for log in m3_results["S2"].evidence[0].related_logs if log.component == "turn-01"]
    assert turn
    assert all(log.on_path is False for log in turn)
    assert any("CPU load high" in log.message for log in turn)


def test_s6_missing_turn_metrics_and_informational_logs(m3_results: dict[str, M3Result]) -> None:
    item = m3_results["S6"].evidence[0]
    assert any("turn-01/turn_cpu_pct" in text and "100% sample null" in text for text in item.missing_evidence)
    assert any("turn-01: không quan sát thấy log" in text for text in item.missing_evidence)
    assert all(log.component == "alice" for log in item.related_logs)
    assert len(item.missing_evidence) == len(set(item.missing_evidence))


def test_debug_and_other_call_logs_do_not_hide_missing_evidence(m3_results: dict[str, M3Result]) -> None:
    result = m3_results["S6"]
    bundle = result.bundle.model_copy(deep=True)
    bundle.meta.missing_sources.append(bundle.meta.missing_sources[0])
    existing = next(log for log in bundle.logs if log.component == "turn-01")
    bundle.logs.append(existing.model_copy(update={
        "log_id": "log-999", "ts": at(bundle.meta.start_ts, 80),
        "level": LogLevel.INFO, "call_id": "unrelated-call", "message": "another call info",
    }))
    evidence = correlate(bundle, result.phases, result.anomalies, result.path)
    assert any("turn-01: không quan sát thấy log" in text for text in evidence[0].missing_evidence)
    assert len(evidence[0].missing_evidence) == len(set(evidence[0].missing_evidence))


def test_warn_from_other_call_is_retained_even_with_low_score(m3_results: dict[str, M3Result]) -> None:
    result = m3_results["S1"]
    bundle = result.bundle.model_copy(deep=True)
    bundle.logs.append(bundle.logs[0].model_copy(update={
        "log_id": "log-999", "ts": result.evidence[0].window_start,
        "call_id": "another-call", "component": "off-path-component",
        "level": LogLevel.WARN, "category": LogCategory.SYSTEM, "message": "external warning",
    }))
    warning = next(log for log in correlate(bundle, result.phases, result.anomalies, result.path)[0].related_logs if log.log_id == "log-999")
    assert warning.same_call is False and warning.on_path is False and warning.score == 0


def test_window_boundaries_are_inclusive(m3_results: dict[str, M3Result]) -> None:
    result = m3_results["S1"]
    bundle = result.bundle.model_copy(deep=True)
    item = result.evidence[0]
    for i, ts in enumerate((item.window_start, item.window_end, item.window_start - timedelta(milliseconds=1), item.window_end + timedelta(milliseconds=1))):
        bundle.logs.append(bundle.logs[0].model_copy(update={
            "log_id": f"boundary-{i}", "ts": ts, "level": LogLevel.ERROR,
        }))
    ids = {log.log_id for log in correlate(bundle, result.phases, result.anomalies, result.path)[0].related_logs}
    assert {"boundary-0", "boundary-1"} <= ids
    assert not {"boundary-2", "boundary-3"} & ids


def test_failed_phase_takes_precedence_over_incidents(m3_results: dict[str, M3Result]) -> None:
    failed, degraded = m3_results["S3"], m3_results["S1"]
    evidence = correlate(failed.bundle, failed.phases, degraded.anomalies, failed.path)
    assert len(evidence) == 1 and evidence[0].focus == EvidenceFocus.PHASE_FAILURE
    assert evidence[0].resource_anomaly_ids == []


def test_none_focus_falls_back_to_call_and_unknown_clock(m3_results: dict[str, M3Result]) -> None:
    result = m3_results["S0"]
    bundle = result.bundle.model_copy(deep=True)
    bundle.meta.clock_model = "unsynchronized"
    evidence = correlate(bundle, [], result.anomalies, result.path)
    assert evidence[0].window_start == bundle.meta.start_ts
    assert evidence[0].window_end == bundle.meta.end_ts
    assert "chưa xác minh" in evidence[0].clock_alignment
    assert all(log.level in {LogLevel.WARN, LogLevel.ERROR} for log in evidence[0].related_logs)


@pytest.mark.parametrize("sid", REGISTRY)
def test_evidence_round_trip_determinism_and_input_independence(sid: str, m3_results: dict[str, M3Result]) -> None:
    result = m3_results[sid]
    before = (result.bundle.model_dump_json(), result.path.model_dump_json(), result.anomalies.model_dump_json())
    evidence = correlate(result.bundle, result.phases, result.anomalies, result.path)
    assert evidence == result.evidence
    assert all(EvidenceBundle.model_validate_json(item.model_dump_json()) == item for item in evidence)
    evidence[0].path.media_components.append("mutation")
    assert (result.bundle.model_dump_json(), result.path.model_dump_json(), result.anomalies.model_dump_json()) == before
    assert build_path_context(result.bundle, extract_selected_path(result.bundle)) == result.path
