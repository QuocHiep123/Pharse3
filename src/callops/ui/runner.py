"""Chạy scenario / phân tích lại dữ liệu upload thành RunResult (dùng InMemoryStore, không Docker/LLM)."""

from __future__ import annotations

import logging
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any

from pydantic import ValidationError

from callops.diagnosis import DiagnosisService, FactExtractor, InferenceEngine, Window
from callops.models import CallEvent, MediaPath, QoSSample
from callops.scenarios import Scenario
from callops.simulator import CallSimulator
from callops.storage import EVENTS_INDEX, QOS_INDEX, InMemoryStore
from callops.ui.contracts import RuleTrace, RunResult, UiInputError

__all__ = ["RunResult", "RuleTrace", "UiInputError", "DEFAULT_SEED", "capture_logs", "run_scenario", "reanalyze"]

DEFAULT_SEED: int = 42  # bằng Settings.seed mặc định


class _ListHandler(logging.Handler):
    def __init__(self, sink: list[str]) -> None:
        super().__init__(logging.DEBUG)
        self.sink = sink

    def emit(self, record: logging.LogRecord) -> None:
        name = record.name.removeprefix("callops.")
        self.sink.append(f"{record.levelname:<7} {name:<10} | {record.getMessage()}")


@contextmanager
def capture_logs(level: int = logging.DEBUG) -> Iterator[list[str]]:
    """Bắt log của logger `callops` vào list (không màu ANSI); khôi phục handler/level cũ khi thoát."""
    lg = logging.getLogger("callops")
    old_level = lg.level
    lines: list[str] = []
    handler = _ListHandler(lines)
    lg.addHandler(handler)
    lg.setLevel(level)
    try:
        yield lines
    finally:
        lg.removeHandler(handler)
        lg.setLevel(old_level)


def _trace(
    events_dicts: list[dict[str, Any]], samples: list[QoSSample]
) -> tuple[tuple[Window, ...], tuple[RuleTrace, ...]]:
    """Chạy lại extractor + từng rule để biết rule nào sinh INFERENCE nào (engine mới -> id trùng report)."""
    bundle = FactExtractor().extract(events_dicts, samples)
    engine = InferenceEngine()
    traces = tuple(RuleTrace(name, tuple(i.id for i in rule(bundle))) for name, rule in engine.rules)
    return tuple(bundle.windows), traces


def _collect(store: InMemoryStore, call_id: str) -> tuple[list[dict[str, Any]], list[CallEvent], list[QoSSample]]:
    ev_dicts = store.search(EVENTS_INDEX, call_id)
    events = sorted((CallEvent.model_validate(d) for d in ev_dicts), key=lambda e: e.ts)
    samples = sorted((QoSSample.model_validate(d) for d in store.search(QOS_INDEX, call_id)),
                     key=lambda s: (s.ts, s.participant_id))
    return ev_dicts, events, samples


def run_scenario(scenario: Scenario, seed: int = DEFAULT_SEED) -> RunResult:
    store = InMemoryStore()
    with capture_logs() as lines:
        result = CallSimulator(scenario, store, seed=seed).run()
        report = DiagnosisService(store).diagnose(result.call_id, scenario.name)
    ev_dicts, events, samples = _collect(store, result.call_id)
    windows, traces = _trace(ev_dicts, samples)
    return RunResult(
        scenario_name=scenario.name, source="simulated", call_id=result.call_id,
        events=tuple(events), samples=tuple(samples), report=report, windows=windows,
        rule_traces=traces, scenario=scenario, log_lines=tuple(lines),
    )


def _derive_call_state(events: Sequence[CallEvent]) -> dict[str, str]:
    """Suy ra call state (state cuối + media_path hợp lệ cuối cùng) từ danh sách event."""
    ordered = sorted(events, key=lambda e: e.ts)
    state: dict[str, str] = {}
    if not ordered:
        return state
    state["state"] = ordered[-1].state.value
    valid = {m.value for m in MediaPath}
    for ev in reversed(ordered):
        if "media_path" in ev.detail:
            val = ev.detail["media_path"]
            if val in valid:
                state["media_path"] = val
            break
    return state


def reanalyze(
    events: Sequence[CallEvent], samples: Sequence[QoSSample], *, scenario_name: str = "uploaded"
) -> RunResult:
    if not events and not samples:
        raise UiInputError("Không có sự kiện hay mẫu QoS nào để phân tích")
    ids = sorted({e.call_id for e in events} | {s.call_id for s in samples})
    if len(ids) > 1:
        raise UiInputError(f"Dữ liệu chứa nhiều call_id ({', '.join(ids)}); chỉ phân tích 1 cuộc gọi mỗi lần")
    call_id = ids[0]

    store = InMemoryStore()
    for e in events:
        store.index(EVENTS_INDEX, e.model_dump(mode="json"))
    for s in samples:
        store.index(QOS_INDEX, s.model_dump(mode="json"))
    store.set_call_state(call_id, _derive_call_state(events))

    try:
        with capture_logs() as lines:
            report = DiagnosisService(store).diagnose(call_id, scenario_name)
        ev_dicts, evs, sams = _collect(store, call_id)
        windows, traces = _trace(ev_dicts, sams)
    except ValidationError as exc:
        raise UiInputError(f"Dữ liệu không đủ để dựng báo cáo chẩn đoán: {exc}") from exc
    return RunResult(
        scenario_name=scenario_name, source="uploaded", call_id=call_id,
        events=tuple(evs), samples=tuple(sams), report=report, windows=windows,
        rule_traces=traces, scenario=None, log_lines=tuple(lines),
    )
