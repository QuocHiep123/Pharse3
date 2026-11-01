"""Rule ice_failure_root_cause: phân biệt 'chưa cấu hình TURN' với 'có TURN nhưng không tới được'."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from callops.diagnosis import FactExtractor, InferenceEngine

T0 = datetime(2026, 10, 31, 9, 0, 0, tzinfo=timezone.utc)


def _ev(event: str, level: str = "INFO", code: str | None = None, **detail: Any) -> dict[str, Any]:
    return {"ts": T0.isoformat(), "call_id": "c1", "level": level, "event": event, "state": "ICE_CHECKING",
            "error_code": code, "message": f"{event} msg", "detail": detail}


def _infer(ice_failed_detail: dict[str, Any]) -> Any:
    events = [
        _ev("ICE_GATHERING_COMPLETE", participant="alice"),
        _ev("ICE_FAILED", "ERROR", "ICE_FAILED", **ice_failed_detail),
        _ev("CALL_FAILED", "ERROR", "ICE_FAILED", reason="x"),
    ]
    bundle = FactExtractor().extract(events, [])
    out = [i for i in InferenceEngine().infer(bundle) if "ICE" in i.hypothesis]
    assert len(out) == 1
    return out[0]


def test_no_turn_keeps_original_conclusion() -> None:
    inf = _infer({"turn_configured": False, "pairs_checked": 9})
    assert "không có đường TURN relay" in inf.hypothesis
    assert "Cấu hình TURN" in (inf.recommendation or "")


def test_unknown_turn_config_keeps_original_conclusion() -> None:
    inf = _infer({})
    assert "không có đường TURN relay" in inf.hypothesis


def test_turn_configured_but_unreachable_is_not_blamed_on_missing_turn() -> None:
    inf = _infer({"turn_configured": True, "relay_only": True, "reason": "ice_timeout"})
    assert "đã cấu hình TURN" in inf.hypothesis
    assert "không có đường TURN relay" not in inf.hypothesis
    rec = inf.recommendation or ""
    assert "credential" in rec and "3478" in rec
    assert "Cấu hình TURN (UDP 3478" not in rec  # không khuyên 'thêm TURN' khi đã có


def test_reasoning_never_starts_with_empty_clause() -> None:
    for detail in ({}, {"turn_configured": False}, {"turn_configured": True, "reason": "no_candidates"}):
        inf = _infer(detail)
        assert not inf.reasoning.lstrip().startswith("."), inf.reasoning
        assert len(inf.reasoning) > 30


def test_reason_is_surfaced_in_reasoning() -> None:
    inf = _infer({"turn_configured": True, "relay_only": True, "reason": "no_candidates"})
    assert "candidate" in inf.reasoning
    inf2 = _infer({"turn_configured": True, "reason": "ice_timeout"})
    assert "thời gian" in inf2.reasoning


def test_inference_still_cites_existing_facts() -> None:
    inf = _infer({"turn_configured": True, "reason": "ice_timeout"})
    assert inf.derived_from and all(f.startswith("F") for f in inf.derived_from)
