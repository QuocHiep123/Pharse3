"""Test contracts nền của callops.ui (dữ liệu dựng tay, không chạy simulator)."""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone

import pytest

from callops.models import CallEvent, CallState, DiagnosisReport, Fact, Inference, QoSSample, Severity
from callops.ui.contracts import STEP_TITLES_VI, FlowStep, RuleTrace, RunResult, UiInputError


def _ts(s: int) -> datetime:
    return datetime(2026, 1, 1, 9, 0, s, tzinfo=timezone.utc)


def _report() -> DiagnosisReport:
    facts = [
        Fact(id="F01", ts=_ts(0), source="log", statement="a", evidence="e1"),
        Fact(id="F02", ts=_ts(1), source="metric", statement="b", evidence="e2"),
    ]
    inf = Inference(id="I01", hypothesis="h", reasoning="r", derived_from=["F02", "F01"], confidence=0.8)
    return DiagnosisReport(call_id="c1", scenario="s", verdict=Severity.WARNING, media_path=None,
                           facts=facts, inferences=[inf])


def _result(events: bool = True) -> RunResult:
    evs = tuple(
        CallEvent(ts=_ts(s), call_id="c1", event="E", state=CallState.SETUP, message="m") for s in (0, 2)
    ) if events else ()
    smp = tuple(
        QoSSample(ts=_ts(s), call_id="c1", participant_id="alice", t_s=s, rtt_ms=1, jitter_ms=1,
                  packet_loss_pct=0, mos=4.0, video_freeze_count=0, concealment_pct=0)
        for s in (1, 5)
    ) if events else ()
    return RunResult(
        scenario_name="s", source="uploaded", call_id="c1", events=evs, samples=smp, report=_report(),
        windows=(), rule_traces=(RuleTrace("r_a", ("I01",)), RuleTrace("r_b", ())),
    )


def test_time_axis() -> None:
    r = _result()
    assert r.t0 == _ts(0)
    assert r.rel_t(_ts(2)) == 2.0
    assert r.duration_s == 6.0


def test_cited_facts_order_and_missing_inference() -> None:
    r = _result()
    assert [f.id for f in r.cited_facts("I01")] == ["F02", "F01"]
    assert [f.id for f in r.facts] == ["F01", "F02"]
    with pytest.raises(KeyError):
        r.inference("I99")
    assert r.inference("I01").id == "I01"


def test_rule_of_and_matched() -> None:
    r = _result()
    assert r.rule_of("I01") == "r_a"
    assert r.rule_of("I99") is None
    assert RuleTrace("r_b", ()).matched is False
    assert RuleTrace("r_a", ("I01",)).matched is True


def test_frozen() -> None:
    r = _result()
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.call_id = "x"  # type: ignore[misc]


def test_empty_result() -> None:
    r = _result(events=False)
    assert r.t0 is None
    assert r.duration_s == 0.0
    assert r.rel_t(_ts(3)) == 0.0


def test_ui_input_error_and_flowstep() -> None:
    assert issubclass(UiInputError, ValueError)

    def step(level: str) -> FlowStep:
        return FlowStep(seq=1, step_no=1, t=0.0, actor_from="a", actor_to="b", event="E", title="t",
                        message="m", explain_vi="x", log_ref="E @ now", level=level)

    assert step("ERROR").is_problem is True
    assert step("INFO").is_problem is False


def test_step_titles() -> None:
    assert set(STEP_TITLES_VI) == {1, 2, 3, 4, 5, 6}
