"""Test end-to-end: mô phỏng -> store -> chẩn đoán, cho từng kịch bản."""

import pytest
from pydantic import ValidationError

from callops.diagnosis import DiagnosisService
from callops.models import CallState, DiagnosisReport, Fact, Inference, MediaPath, Severity
from callops.scenarios import SCENARIOS
from callops.simulator import CallSimulator
from callops.storage import EVENTS_INDEX, InMemoryStore


def run(name: str) -> tuple[DiagnosisReport, InMemoryStore]:
    store = InMemoryStore()
    result = CallSimulator(SCENARIOS[name], store, seed=42).run()
    return DiagnosisService(store).diagnose(result.call_id, name), store


@pytest.mark.parametrize(
    ("name", "path", "verdict"),
    [
        ("p2p_good", MediaPath.P2P_STUN, Severity.OK),
        ("same_lan", MediaPath.P2P_HOST, Severity.OK),
        ("symmetric_nat_turn", MediaPath.TURN_RELAY, Severity.OK),
        ("ice_failed_no_turn", None, Severity.CRITICAL),
        ("congestion", MediaPath.P2P_STUN, Severity.CRITICAL),
        ("wifi_loss", MediaPath.P2P_STUN, Severity.WARNING),
        ("group_sfu", MediaPath.SFU, Severity.CRITICAL),
    ],
)
def test_scenario_path_and_verdict(name: str, path: MediaPath | None, verdict: Severity) -> None:
    report, _ = run(name)
    assert report.media_path == path
    assert report.verdict == verdict


def test_call_state_machine_order() -> None:
    _, store = run("p2p_good")
    states = [e["state"] for e in store._docs[EVENTS_INDEX]]
    order = [CallState.SETUP, CallState.OFFER_SENT, CallState.ANSWER_RECEIVED, CallState.ICE_CHECKING,
             CallState.CONNECTED, CallState.TERMINATED]
    firsts = [states.index(s.value) for s in order]
    assert firsts == sorted(firsts)


def test_every_fact_has_evidence_and_every_inference_cites_facts() -> None:
    for name in SCENARIOS:
        report, _ = run(name)
        ids = {f.id for f in report.facts}
        assert report.inferences, name
        for f in report.facts:
            assert f.ts and f.evidence
        for i in report.inferences:
            assert i.derived_from and set(i.derived_from) <= ids


def test_congestion_vs_random_loss_are_distinguished() -> None:
    cong, _ = run("congestion")
    wifi, _ = run("wifi_loss")
    assert any("Nghẽn" in i.hypothesis and "bob" in i.hypothesis for i in cong.inferences)
    assert any("ngẫu nhiên" in i.hypothesis for i in wifi.inferences)
    assert not any("Nghẽn" in i.hypothesis for i in wifi.inferences)


def test_ice_failure_root_cause_cites_error_log() -> None:
    report, _ = run("ice_failed_no_turn")
    inf = next(i for i in report.inferences if "ICE thất bại" in i.hypothesis)
    cited = [f for f in report.facts if f.id in inf.derived_from]
    assert any(f.error_code == "ICE_FAILED" for f in cited)
    assert any(f.error_code == "STUN_TIMEOUT" for f in cited)


def test_group_sfu_blames_only_dave() -> None:
    report, _ = run("group_sfu")
    iso = next(i for i in report.inferences if "last-mile" in i.hypothesis)
    assert "dave" in iso.hypothesis and "alice" not in iso.hypothesis


def test_report_rejects_inference_without_fact() -> None:
    fact = Fact(id="F01", ts="2026-10-30T09:00:00Z", source="log", statement="x", evidence="raw")
    with pytest.raises(ValidationError):
        DiagnosisReport(call_id="c", scenario="s", verdict=Severity.OK, media_path=None, facts=[fact],
                        inferences=[Inference(id="I01", hypothesis="h", reasoning="r", derived_from=["F99"],
                                              confidence=0.5)])
    with pytest.raises(ValidationError):
        Inference(id="I01", hypothesis="h", reasoning="r", derived_from=[], confidence=0.5)
