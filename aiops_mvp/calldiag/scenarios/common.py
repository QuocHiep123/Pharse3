"""Reusable timeline segments; offsets and shared data are defined in scenarios.data."""

from collections.abc import Iterable, Mapping
from math import ceil, floor
from typing import Any, Literal

from calldiag import config
from calldiag.models import CallTelemetry, Direction, EventType, LogCategory, LogLevel, MetricName
from calldiag.scenarios import data
from calldiag.scenarios.builder import Plateau, Profile, ScenarioBuilder

EventSpec = tuple[float, str, str, dict[str, Any]]
LogSpec = tuple[float, str, str, str, bool, str]


def _add_events(b: ScenarioBuilder, events: Iterable[EventSpec], offset: float = 0.0) -> None:
    for t, component, event, attrs in events:
        b.event(offset + t, component, EventType(event), **attrs)


def add_logs(b: ScenarioBuilder, logs: Iterable[LogSpec], offset: float = 0.0) -> None:
    for t, component, level, category, call_scoped, message in logs:
        b.log(offset + t, component, LogLevel(level), LogCategory(category), message, call_scoped=call_scoped)


def add_setup(b: ScenarioBuilder) -> None:
    _add_events(b, data.SETUP_EVENTS)
    add_logs(b, data.SETUP_LOGS)


def add_offer_answer_ok(b: ScenarioBuilder) -> None:
    _add_events(b, data.OFFER_ANSWER_EVENTS)
    add_logs(b, data.OFFER_ANSWER_LOGS)


def add_offer_answer_timeout(b: ScenarioBuilder) -> None:
    _add_events(b, data.TIMEOUT_EVENTS)
    add_logs(b, data.TIMEOUT_LOGS)


def add_ice(b: ScenarioBuilder, mode: Literal["p2p", "relay", "fail"]) -> float | None:
    if mode not in data.ICE_PAIR_CHECKS:
        raise ValueError(f"Unsupported ICE mode: {mode}")
    _add_events(b, data.ICE_GATHERING_EVENTS)
    add_logs(b, (data.TURN_ALLOCATION_LOG,))
    for t, local, remote, succeeded in data.ICE_PAIR_CHECKS[mode]:
        event = EventType.ICE_PAIR_SUCCEEDED if succeeded else EventType.ICE_PAIR_FAILED
        attrs: dict[str, Any] = {"local_type": local, "remote_type": remote}
        if not succeeded:
            attrs["error"] = "timeout"
            b.log(t, config.CALLER, LogLevel.WARN, LogCategory.ICE, f"candidate pair {local}↔{remote} failed: timeout")
        b.event(t, config.CALLER, event, **attrs)
    if mode == "fail":
        _add_events(b, data.ICE_FAILURE_EVENTS)
        add_logs(b, data.ICE_FAILURE_LOGS)
        return None

    relay = mode == "relay"
    local = "relay" if relay else "srflx"
    selected_t = data.ICE_SELECTED_T[mode]
    b.event(selected_t, config.CALLER, EventType.ICE_SELECTED_PAIR,
            local_type=local, remote_type="srflx", via_turn=relay,
            turn_server=config.TURN_SERVER if relay else None)
    message = f"selected candidate pair {local}↔srflx"
    if relay:
        message += f" via {config.TURN_SERVER}"
    b.log(selected_t, config.CALLER, LogLevel.INFO, LogCategory.ICE, message)
    connected_t = data.ICE_CONNECTED_T[mode]
    b.event(connected_t, config.CALLER, EventType.ICE_CONNECTED)
    return connected_t


def add_media_start(b: ScenarioBuilder, tc: float) -> None:
    _add_events(b, data.MEDIA_EVENTS, offset=tc)
    add_logs(b, data.MEDIA_LOGS, offset=tc)


def add_termination_normal(b: ScenarioBuilder, t: float = data.NORMAL_HANGUP_T) -> None:
    b.event(t, config.CALLER, EventType.HANGUP, by=config.CALLER, reason="normal")
    b.event(t + data.TERMINATION_DELAY_SEC, config.SIGNALING, EventType.CALL_ENDED, reason="normal")
    b.log(t, config.SIGNALING, LogLevel.INFO, LogCategory.SIGNALING, "HANGUP from alice")
    b.log(t + data.TERMINATION_DELAY_SEC, config.SIGNALING, LogLevel.INFO, LogCategory.SIGNALING, "call ended reason=normal")


def add_background_logs(
    b: ScenarioBuilder, *, media_from: float | None, media_to: float | None,
    relay: bool, end_t: float,
) -> None:
    if media_from is not None and media_to is not None:
        for t in range(data.MEDIA_SNAPSHOT_INTERVAL_SEC, floor(media_to) + 1, data.MEDIA_SNAPSHOT_INTERVAL_SEC):
            if t >= media_from:
                b.log(t, config.CALLER, LogLevel.DEBUG, LogCategory.MEDIA, "getStats snapshot ok")
        if relay:
            for t in range(data.TURN_REFRESH_INTERVAL_SEC, floor(media_to) + 1, data.TURN_REFRESH_INTERVAL_SEC):
                if t >= media_from:
                    b.log(t, config.TURN_SERVER, LogLevel.DEBUG, LogCategory.TURN, "allocation refresh ok")
    if end_t >= data.OTHER_CALL_LOG_MIN_END_T and end_t >= data.OTHER_CALL_LOG_T:
        b.log(data.OTHER_CALL_LOG_T, config.TURN_SERVER, LogLevel.INFO, LogCategory.TURN,
              "allocation created for another call", other_call_id=data.OTHER_CALL_ID)


def add_standard_metrics(
    b: ScenarioBuilder, *, qos: dict[MetricName, Profile] | None,
    turn_cpu: Profile, client_cpu: Profile, end_t: float,
) -> None:
    if qos is not None:
        for metric in (MetricName.RTT_MS, MetricName.JITTER_MS, MetricName.PACKET_LOSS_PCT, MetricName.BITRATE_KBPS):
            b.series(config.CALLER, Direction(config.METRIC_META[metric]["direction"]), metric,
                     data.QOS_FROM_T, min(data.QOS_TO_T, ceil(end_t) - 1), qos[metric])
    b.series(config.TURN_SERVER, Direction.NONE, MetricName.TURN_CPU_PCT,
             0, floor(end_t), turn_cpu, call_scoped=False)
    b.series(config.CALLER, Direction.NONE, MetricName.CLIENT_CPU_PCT,
             0, floor(end_t), client_cpu)


def new_builder(sid: str) -> ScenarioBuilder:
    return ScenarioBuilder(scenario_id=sid, title=data.SCENARIO_TITLES[sid],
                           call_id=data.SCENARIO_CALL_IDS[sid], seed=data.SCENARIO_SEEDS[sid])


def qos_profiles(
    baseline: Mapping[str, tuple[float, float]] = data.BASE_QOS,
    plateaus: Mapping[str, tuple[float, float, float, float]] | None = None,
) -> dict[MetricName, Profile]:
    return {
        MetricName(name): Profile(mean, std, (Plateau(*plateaus[name]),) if plateaus and name in plateaus else ())
        for name, (mean, std) in baseline.items()
    }


def build_media_scenario(
    b: ScenarioBuilder, *, mode: Literal["p2p", "relay"], qos: dict[MetricName, Profile],
    turn_cpu: Profile, logs: Iterable[LogSpec] = (), missing_sources: list[str] | None = None,
) -> CallTelemetry:
    add_setup(b)
    add_offer_answer_ok(b)
    connected_t = add_ice(b, mode)
    assert connected_t is not None
    add_media_start(b, connected_t)
    add_termination_normal(b)
    media_from = connected_t + data.MEDIA_EVENTS[-1][0]
    add_background_logs(b, media_from=media_from, media_to=data.QOS_TO_T,
                        relay=mode == "relay", end_t=data.MEDIA_END_T)
    add_logs(b, logs)
    add_standard_metrics(b, qos=qos, turn_cpu=turn_cpu,
                         client_cpu=Profile(*data.CLIENT_CPU), end_t=data.MEDIA_END_T)
    return b.build(end_t=data.MEDIA_END_T, expected_metrics=list(data.EXPECTED_METRICS_MEDIA),
                   missing_sources=list(data.MISSING_SOURCES) if missing_sources is None else missing_sources)
