"""Test biểu đồ QoS Plotly (ui/charts.py)."""

from __future__ import annotations

from datetime import timedelta

import pytest

pytest.importorskip("plotly")

from callops.diagnosis import FactExtractor  # noqa: E402
from callops.models import QoSSample  # noqa: E402
from callops.qos import THRESHOLDS, Threshold  # noqa: E402
from callops.scenarios import SCENARIOS  # noqa: E402
from callops.simulator import CallSimulator  # noqa: E402
from callops.storage import EVENTS_INDEX, QOS_INDEX, InMemoryStore  # noqa: E402
from callops.ui.charts import METRICS, qos_figure  # noqa: E402


def build(name: str):
    store = InMemoryStore()
    result = CallSimulator(SCENARIOS[name], store, seed=42).run()
    events = store.search(EVENTS_INDEX, result.call_id)
    samples = [QoSSample.model_validate(d) for d in store.search(QOS_INDEX, result.call_id)]
    bundle = FactExtractor().extract(events, samples)
    return samples, bundle.windows


def hlines(fig):
    return [s for s in fig.layout.shapes if s.type == "line" and s.y0 == s.y1]


def rects(fig):
    return [s for s in fig.layout.shapes if s.type == "rect"]


def test_congestion_traces_and_thresholds():
    samples, windows = build("congestion")
    fig = qos_figure(samples, windows=windows)
    assert len(fig.data) == 8
    assert {tr.name for tr in fig.data} == {"alice", "bob"}
    assert len(hlines(fig)) == 8


def test_incident_windows_as_vrect():
    samples, windows = build("congestion")
    fig = qos_figure(samples, windows=windows)
    names = {m for m, _ in METRICS}
    assert len(rects(fig)) == len([w for w in windows if w.metric in names])
    assert any(r.x0 >= 10 for r in rects(fig))


def test_group_sfu_traces():
    samples, _ = build("group_sfu")
    assert len(qos_figure(samples).data) == 16


def test_custom_thresholds():
    samples, _ = build("congestion")
    custom = dict(THRESHOLDS)
    custom["rtt_ms"] = Threshold(111, 222)
    ys = {s.y0 for s in hlines(qos_figure(samples, custom))}
    assert {111, 222} <= ys


def test_cursor_line():
    samples, _ = build("congestion")
    fig = qos_figure(samples, cursor_t=12.5)
    assert any(s.type == "line" and s.x0 == s.x1 == 12.5 for s in fig.layout.shapes)


def test_empty_samples():
    fig = qos_figure([])
    assert len(fig.data) == 0
    assert "Không có dữ liệu" in fig.layout.annotations[0].text


def test_custom_t0_offsets_x():
    samples, _ = build("congestion")
    first = min(s.ts for s in samples)
    fig = qos_figure(samples, t0=first - timedelta(seconds=5))
    assert min(min(tr.x) for tr in fig.data) == 5.0
