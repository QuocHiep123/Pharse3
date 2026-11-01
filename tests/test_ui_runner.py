"""Test callops.ui.runner: chạy scenario / re-analyze ra RunResult (không cần Docker/LLM)."""

from __future__ import annotations

import logging

import pytest

from callops.diagnosis import InferenceEngine
from callops.models import MediaPath, Severity
from callops.scenarios import SCENARIOS
from callops.ui.runner import (
    UiInputError,
    _derive_call_state,
    reanalyze,
    run_scenario,
)

EXPECTED = {
    "p2p_good": (MediaPath.P2P_STUN, Severity.OK),
    "same_lan": (MediaPath.P2P_HOST, Severity.OK),
    "symmetric_nat_turn": (MediaPath.TURN_RELAY, Severity.OK),
    "ice_failed_no_turn": (None, Severity.CRITICAL),
    "congestion": (MediaPath.P2P_STUN, Severity.CRITICAL),
    "wifi_loss": (MediaPath.P2P_STUN, Severity.WARNING),
    "group_sfu": (MediaPath.SFU, Severity.CRITICAL),
}


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_run_scenario_contract(name: str) -> None:
    r = run_scenario(SCENARIOS[name])
    assert r.source == "simulated"
    assert r.scenario is SCENARIOS[name]
    assert r.report.inferences
    fact_ids = {f.id for f in r.report.facts}
    for inf in r.report.inferences:
        assert set(inf.derived_from) <= fact_ids
    assert [t.rule for t in r.rule_traces] == [n for n, _ in InferenceEngine().rules]
    flat = [i for t in r.rule_traces for i in t.inference_ids]
    assert flat == [i.id for i in r.report.inferences]
    assert {w.fact_id for w in r.windows} <= fact_ids
    ts = [e.ts for e in r.events]
    assert ts == sorted(ts)


@pytest.mark.parametrize(("name", "expected"), sorted(EXPECTED.items()))
def test_verdict_and_media_path(name: str, expected: tuple[MediaPath | None, Severity]) -> None:
    r = run_scenario(SCENARIOS[name])
    assert (r.report.media_path, r.report.verdict) == expected


def test_deterministic() -> None:
    a = run_scenario(SCENARIOS["congestion"], seed=42)
    b = run_scenario(SCENARIOS["congestion"], seed=42)
    assert a.call_id == b.call_id
    assert [f.statement for f in a.facts] == [f.statement for f in b.facts]


def test_log_capture_restores_logger() -> None:
    lg = logging.getLogger("callops")
    level, handlers = lg.level, list(lg.handlers)
    r = run_scenario(SCENARIOS["p2p_good"])
    assert r.log_lines
    assert any("[STEP 1]" in line for line in r.log_lines)
    assert lg.level == level
    assert lg.handlers == handlers


@pytest.mark.parametrize("name", ["congestion", "ice_failed_no_turn", "group_sfu"])
def test_reanalyze_round_trip(name: str) -> None:
    r = run_scenario(SCENARIOS[name])
    r2 = reanalyze(r.events, r.samples)
    assert r2.source == "uploaded"
    assert r2.scenario is None
    assert r2.report.verdict == r.report.verdict
    assert r2.report.media_path == r.report.media_path
    assert [i.hypothesis for i in r2.report.inferences] == [i.hypothesis for i in r.report.inferences]


def test_reanalyze_empty() -> None:
    with pytest.raises(UiInputError):
        reanalyze([], [])


def test_reanalyze_multiple_call_ids() -> None:
    r = run_scenario(SCENARIOS["p2p_good"])
    events = list(r.events)
    events[0] = events[0].model_copy(update={"call_id": "other"})
    with pytest.raises(UiInputError, match="other"):
        reanalyze(events, r.samples)


def test_reanalyze_insufficient_data_is_ui_error() -> None:
    r = run_scenario(SCENARIOS["p2p_good"])
    invite = [e for e in r.events if e.event == "INVITE"][:1]
    with pytest.raises(UiInputError):
        reanalyze(invite, [])


def test_derive_call_state_ignores_bogus_media_path() -> None:
    r = run_scenario(SCENARIOS["p2p_good"])
    ev = r.events[-1].model_copy(update={"detail": {"media_path": "BOGUS"}})
    assert "media_path" not in _derive_call_state([ev])
    ok = r.events[-1].model_copy(update={"detail": {"media_path": "SFU"}})
    assert _derive_call_state([ok]) == {"state": ok.state.value, "media_path": "SFU"}
