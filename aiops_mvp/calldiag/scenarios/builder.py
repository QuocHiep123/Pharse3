"""Seeded telemetry builder and interpolated metric profiles."""

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np

from calldiag import config
from calldiag.io import validate_bundle
from calldiag.models import (
    EVENT_PHASE, CallMeta, CallTelemetry, Direction, EventType, LogCategory,
    LogLevel, LogRecord, MetricName, MetricSample, TraceEvent,
)
from calldiag.utils import at


@dataclass(frozen=True)
class Plateau:
    t_start: float
    t_end: float
    mean: float
    std: float
    ramp_in: float = config.DEFAULT_RAMP_IN_SEC
    ramp_out: float = config.DEFAULT_RAMP_OUT_SEC

    def __post_init__(self) -> None:
        if self.t_end < self.t_start or min(self.std, self.ramp_in, self.ramp_out) < 0:
            raise ValueError("Plateau requires t_end >= t_start and nonnegative std/ramps")

    def weight(self, t: float) -> float:
        if self.t_start <= t <= self.t_end:
            return 1.0
        if self.ramp_in > 0 and self.t_start - self.ramp_in < t < self.t_start:
            return (t - (self.t_start - self.ramp_in)) / self.ramp_in
        if self.ramp_out > 0 and self.t_end < t < self.t_end + self.ramp_out:
            return 1.0 - (t - self.t_end) / self.ramp_out
        return 0.0


@dataclass(frozen=True)
class Profile:
    base_mean: float
    base_std: float
    plateaus: tuple[Plateau, ...] = ()
    missing: bool = False

    def __post_init__(self) -> None:
        if self.base_std < 0:
            raise ValueError("Profile requires nonnegative base_std")

    def parameters_at(self, t: float) -> tuple[float, float]:
        if not self.plateaus:
            return self.base_mean, self.base_std
        plateau = max(self.plateaus, key=lambda p: p.weight(t))
        weight = plateau.weight(t)
        return (
            self.base_mean + (plateau.mean - self.base_mean) * weight,
            self.base_std + (plateau.std - self.base_std) * weight,
        )


class ScenarioBuilder:
    def __init__(
        self, *, scenario_id: str, title: str, call_id: str, seed: int,
        start: datetime = config.BASE_START,
    ) -> None:
        self.scenario_id = scenario_id
        self.title = title
        self.call_id = call_id
        self.start = start
        self.rng = np.random.default_rng(seed)
        self._events: list[TraceEvent] = []
        self._logs: list[LogRecord] = []
        self._metrics: list[MetricSample] = []

    def event(self, t: float, component: str, type: EventType, **attrs: Any) -> None:
        self._events.append(TraceEvent(
            event_id="", ts=at(self.start, t), call_id=self.call_id,
            phase=EVENT_PHASE[type], component=component, type=type, attrs=deepcopy(attrs),
        ))

    def log(
        self, t: float, component: str, level: LogLevel, category: LogCategory,
        message: str, *, call_scoped: bool = True,
        other_call_id: str | None = None, **attrs: Any,
    ) -> None:
        call_id = other_call_id if other_call_id is not None else self.call_id if call_scoped else None
        self._logs.append(LogRecord(
            log_id="", ts=at(self.start, t), call_id=call_id, component=component,
            level=level, category=category, message=message, attrs=deepcopy(attrs),
        ))

    def series(
        self, source: str, direction: Direction, metric: MetricName,
        t_from: int, t_to: int, profile: Profile, *, call_scoped: bool = True,
    ) -> None:
        if t_from < 0 or t_to < t_from:
            raise ValueError("series requires 0 <= t_from <= t_to")
        for t in range(t_from, t_to + 1, config.SAMPLE_INTERVAL_SEC):
            value = None
            if not profile.missing:
                mean, std = profile.parameters_at(t)
                value = max(0.0, float(mean + self.rng.normal(0, std)))
                if config.METRIC_META[metric]["unit"] == "%":
                    value = min(config.PERCENT_MAX, value)
                value = round(value, config.SAMPLE_DECIMALS)
            self._metrics.append(MetricSample(
                sample_id=f"m-{source}-{metric.value}-{t:04d}",
                ts=at(self.start, t), call_id=self.call_id if call_scoped else None,
                source=source, direction=direction, metric=metric, value=value,
            ))

    def build(
        self, *, end_t: float, expected_metrics: list[str], missing_sources: list[str],
    ) -> CallTelemetry:
        # Python's stable sort preserves insertion order for equal timestamps.
        events = [
            event.model_copy(deep=True, update={"event_id": f"ev-{i:03d}"})
            for i, event in enumerate(sorted(self._events, key=lambda e: e.ts), start=1)
        ]
        logs = [
            log.model_copy(deep=True, update={"log_id": f"log-{i:03d}"})
            for i, log in enumerate(sorted(self._logs, key=lambda log: log.ts), start=1)
        ]
        bundle = CallTelemetry(
            meta=CallMeta(
                call_id=self.call_id, scenario_id=self.scenario_id, title=self.title,
                start_ts=self.start, end_ts=at(self.start, end_t),
                expected_metrics=list(expected_metrics), missing_sources=list(missing_sources),
            ),
            events=events, metrics=[s.model_copy(deep=True) for s in self._metrics], logs=logs,
        )
        validate_bundle(bundle)
        return bundle
