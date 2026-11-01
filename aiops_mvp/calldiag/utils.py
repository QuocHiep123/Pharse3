"""Pure time and metric formatting helpers."""

from datetime import datetime, timedelta

from calldiag import config
from calldiag.models import MetricName


def offset_sec(ts: datetime, start: datetime) -> float:
    return (ts - start).total_seconds()


def at(start: datetime, t: float) -> datetime:
    ts = start + timedelta(seconds=t)
    rounded_microseconds = round(ts.microsecond / config.MILLISECONDS_PER_SECOND) * config.MILLISECONDS_PER_SECOND
    return ts.replace(microsecond=0) + timedelta(microseconds=rounded_microseconds)


def fmt_time(ts: datetime, ms: bool = False) -> str:
    return ts.strftime("%H:%M:%S.%f")[:-3] if ms else ts.strftime("%H:%M:%S")


def fmt_window(a: datetime, b: datetime) -> str:
    return f"{fmt_time(a)}–{fmt_time(b)}"


def fmt_value(metric: MetricName | str, value: float | None) -> str:
    if value is None:
        return "missing"
    meta = config.METRIC_META[metric]
    spacer = "" if meta["unit"] == "%" else " "
    return f"{value:.{meta['decimals']}f}{spacer}{meta['unit']}"
