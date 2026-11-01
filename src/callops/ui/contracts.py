"""Interface chung của callops.ui: các task runner/loaders/flow/charts/views chỉ import từ đây."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from callops.diagnosis import Window
from callops.models import CallEvent, DiagnosisReport, Fact, Inference, QoSSample
from callops.scenarios import Scenario

__all__ = ["UiInputError", "STEP_TITLES_VI", "FlowStep", "RuleTrace", "RunResult"]


class UiInputError(ValueError):
    """Đầu vào người dùng sai/thiếu; thông điệp tiếng Việt, hiển thị thẳng trong UI."""


# 6 bước call flow, khớp README
STEP_TITLES_VI: dict[int, str] = {
    1: "Thiết lập cuộc gọi (signaling)",
    2: "Trao đổi SDP offer/answer",
    3: "ICE gathering (host/srflx/relay)",
    4: "ICE connectivity checks",
    5: "Media + đo QoS",
    6: "Kết thúc cuộc gọi",
}

_PROBLEM_LEVELS = {"WARNING", "ERROR", "CRITICAL"}


@dataclass(frozen=True)
class FlowStep:
    """1 mũi tên trên sequence diagram, dựng từ 1 CallEvent."""

    seq: int
    step_no: int
    t: float  # giây kể từ t0
    actor_from: str
    actor_to: str
    event: str
    title: str
    message: str
    explain_vi: str
    log_ref: str  # f"{event} @ {ts.isoformat()}"
    level: str = "INFO"

    @property
    def is_problem(self) -> bool:
        return self.level in _PROBLEM_LEVELS


@dataclass(frozen=True)
class RuleTrace:
    """Vết 1 rule của InferenceEngine: rule nào sinh INFERENCE nào."""

    rule: str
    inference_ids: tuple[str, ...]  # rỗng = không khớp

    @property
    def matched(self) -> bool:
        return bool(self.inference_ids)


@dataclass(frozen=True)
class RunResult:
    scenario_name: str
    source: Literal["simulated", "uploaded"]
    call_id: str
    events: tuple[CallEvent, ...]  # sort theo ts
    samples: tuple[QoSSample, ...]  # sort theo (ts, participant_id)
    report: DiagnosisReport
    windows: tuple[Window, ...]
    rule_traces: tuple[RuleTrace, ...]
    scenario: Scenario | None = None  # None khi upload
    log_lines: tuple[str, ...] = ()

    @property
    def facts(self) -> list[Fact]:
        return self.report.facts

    @property
    def t0(self) -> datetime | None:
        stamps = [e.ts for e in self.events] + [s.ts for s in self.samples]
        return min(stamps) if stamps else None

    def rel_t(self, ts: datetime) -> float:
        t0 = self.t0
        return (ts - t0).total_seconds() if t0 is not None else 0.0

    @property
    def duration_s(self) -> float:
        # sample đại diện cho 1 giây nên cộng thêm 1s
        values = [self.rel_t(e.ts) for e in self.events] + [self.rel_t(s.ts) + 1 for s in self.samples]
        return max(values) if values else 0.0

    def inference(self, inf_id: str) -> Inference:
        for inf in self.report.inferences:
            if inf.id == inf_id:
                return inf
        raise KeyError(inf_id)

    def cited_facts(self, inf_id: str) -> list[Fact]:
        by_id = {f.id: f for f in self.report.facts}
        return [by_id[fid] for fid in self.inference(inf_id).derived_from]

    def rule_of(self, inf_id: str) -> str | None:
        for trace in self.rule_traces:
            if inf_id in trace.inference_ids:
                return trace.rule
        return None
