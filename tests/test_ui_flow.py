"""Test callops.ui.flow: timeline các bước + SVG sequence diagram."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from callops.models import CallEvent, CallState
from callops.scenarios import SCENARIOS
from callops.simulator import CallSimulator
from callops.storage import EVENTS_INDEX, InMemoryStore
from callops.ui.flow import (
    EVENT_INFO,
    INFRA_ACTORS,
    FlowStep,
    actors_of,
    build_timeline,
    render_flow_svg,
    steps_until,
)


def _events(name: str) -> list[CallEvent]:
    store = InMemoryStore()
    res = CallSimulator(SCENARIOS[name], store, seed=42).run()
    return [CallEvent.model_validate(d) for d in store.search(EVENTS_INDEX, res.call_id)]


def test_p2p_good_timeline() -> None:
    events = _events("p2p_good")
    steps = build_timeline(events)
    assert len(steps) == len(events)
    assert [s.seq for s in steps] == list(range(1, len(steps) + 1))
    assert all(a.t <= b.t for a, b in zip(steps, steps[1:]))
    assert all(a.step_no <= b.step_no for a, b in zip(steps, steps[1:]))
    first, last = steps[0], steps[-1]
    assert (first.event, first.actor_from, first.actor_to) == ("INVITE", "alice", "Signaling")
    assert last.event == "BYE"
    assert first.log_ref == f"INVITE @ {events[0].ts.isoformat()}" or first.log_ref.startswith("INVITE @ ")


def test_event_info_covers_all_scenarios() -> None:
    for name in SCENARIOS:
        for ev in _events(name):
            assert ev.event in EVENT_INFO, (name, ev.event)


def test_symmetric_nat_turn() -> None:
    steps = build_timeline(_events("symmetric_nat_turn"))
    assert any(s.event == "TURN_FALLBACK" and s.actor_to == "TURN" for s in steps)
    assert any(s.event == "MEDIA_ESTABLISHED" and s.actor_to == "TURN" for s in steps)


def test_group_sfu_actors() -> None:
    steps = build_timeline(_events("group_sfu"))
    actors = actors_of(steps)
    for a in ("alice", "bob", "carol", "dave", "SFU"):
        assert a in actors
    assert actors.index("alice") < actors.index("SFU")
    assert any(s.event == "SFU_CONNECTED" and s.actor_from == "carol" for s in steps)
    assert set(INFRA_ACTORS) >= {"SFU"}


def test_ice_failed_no_turn() -> None:
    steps = build_timeline(_events("ice_failed_no_turn"))
    assert any(s.event == "ICE_FAILED" and s.is_problem for s in steps)
    assert not any(s.step_no == 5 for s in steps)


def test_render_upto() -> None:
    steps = build_timeline(_events("p2p_good"))
    svg = render_flow_svg(steps, upto=3)
    assert "<svg" in svg and "<script" not in svg
    assert svg.count('class="step') == 3
    assert svg.count("current") >= 1
    assert svg.count('class="step current"') + svg.count('class="step problem current"') == 1
    for a in actors_of(steps):
        assert a in svg
    assert 'class="step' not in render_flow_svg(steps, upto=0)
    assert render_flow_svg(steps, upto=999).count('class="step') == len(steps)
    assert render_flow_svg(steps).count('class="step') == len(steps)
    assert render_flow_svg(steps, upto=-5).count('class="step') == 0


def test_escape() -> None:
    step = FlowStep(seq=1, step_no=1, t=0.0, actor_from="a<i>", actor_to="Signaling", event="X",
                    title="<b>x</b>", message="<u>m</u>", explain_vi="", log_ref="X @ t")
    svg = render_flow_svg([step])
    assert "&lt;b&gt;" in svg
    assert "<b>x</b>" not in svg and "<u>m</u>" not in svg and "a<i>" not in svg


def test_empty() -> None:
    assert "Không có sự kiện" in render_flow_svg([])


def test_steps_until() -> None:
    steps = build_timeline(_events("p2p_good"))
    assert steps_until(steps, -1) == 0
    assert steps_until(steps, 1e9) == len(steps)


def test_unknown_event() -> None:
    ev = CallEvent(ts=datetime(2026, 1, 1, tzinfo=timezone.utc), call_id="c", event="CUSTOM_X",
                   state=CallState.CONNECTED, message="m")
    (step,) = build_timeline([ev])
    assert step.step_no == 5
    assert step.title == "CUSTOM_X"
    assert (step.actor_from, step.actor_to) == ("Caller", "Signaling")


def test_long_diagram_window_follows_current_step() -> None:
    """Sơ đồ dài hơn khung phải cắt viewBox bám bước hiện tại, và vẫn vẽ hàng actor."""
    import re

    from callops.scenarios import SCENARIOS
    from callops.simulator import CallSimulator
    from callops.storage import EVENTS_INDEX, InMemoryStore
    from callops.ui.flow import _VIEW_H, build_timeline, render_flow_svg

    store = InMemoryStore()
    res = CallSimulator(SCENARIOS["congestion"], store).run()
    steps = build_timeline([CallEvent.model_validate(d) for d in store.search(EVENTS_INDEX, res.call_id)])
    first = render_flow_svg(steps, 1)
    last = render_flow_svg(steps)
    vb = lambda svg: [float(v) for v in re.search(r'viewBox="([^"]+)"', svg).group(1).split()]  # noqa: E731
    assert vb(first)[1] == 0
    assert vb(last)[1] > 0 and vb(last)[3] == _VIEW_H
    assert 'class="actor"' in last and 'class="headbg"' in last
