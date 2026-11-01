"""Pure Plotly figures for the CallDiag UI (plan 09); no Streamlit calls, so tests can build them."""

from collections.abc import Collection, Sequence
from datetime import datetime, timedelta

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from calldiag import config
from calldiag.models import (
    PHASE_LABELS, PHASE_ORDER, AnomalyResult, Fact, MetricCategory, Phase, PhaseSpan, TraceEvent,
)

# Display-only styling, so it lives with the UI rather than in calldiag.config.
STATUS_COLORS = {
    "ok": "#2e7d32", "degraded": "#f9a825", "failed": "#c62828",
    "skipped": "#9e9e9e", "incomplete": "#6d4c41",
}
HIGHLIGHT = "#7b1fa2"
EVENT_COLOR = "#37474f"
INCIDENT_FILL = "rgba(198, 40, 40, 0.12)"
RESOURCE_FILL = "rgba(249, 168, 37, 0.20)"
BASELINE_COLOR = "#757575"
MIN_BAR_MS = 40          # keeps sub-second phases visible on a 2-minute axis
ZOOM_PAD = timedelta(seconds=1)
# Each panel: (title, ((source, metric, dash), ...)).
PANELS: tuple[tuple[str, tuple[tuple[str, str, str], ...]], ...] = (
    ("RTT (ms)", ((config.CALLER, "rtt_ms", "solid"),)),
    ("Jitter (ms)", ((config.CALLER, "jitter_ms", "solid"),)),
    ("Packet loss (%)", ((config.CALLER, "packet_loss_pct", "solid"),)),
    ("Inbound bitrate (kbps)", ((config.CALLER, "bitrate_kbps", "solid"),)),
    ("CPU (%)", ((config.TURN_SERVER, "turn_cpu_pct", "solid"), (config.CALLER, "client_cpu_pct", "dash"))),
)


def phase_waterfall(
    phases: Sequence[PhaseSpan], events: Sequence[TraceEvent],
    highlight_refs: Collection[str] = (), zoom_setup: bool = False,
) -> go.Figure:
    """Gantt of the 5 phases plus one marker per trace event."""
    fig = go.Figure()
    labels = [PHASE_LABELS[phase] for phase in PHASE_ORDER]
    anchor = next((p.start_ts for p in phases if p.start_ts is not None), None)
    for span in sorted(phases, key=lambda p: PHASE_ORDER.index(p.phase)):
        if span.start_ts is not None and span.end_ts is not None:
            duration = max((span.end_ts - span.start_ts).total_seconds() * 1000, MIN_BAR_MS)
            fig.add_trace(go.Bar(
                x=[duration], base=[span.start_ts], y=[span.label], orientation="h",
                marker_color=STATUS_COLORS[span.status.value], opacity=0.85, showlegend=False,
                hovertemplate=(f"<b>{span.label}</b><br>status: {span.status.value}<br>"
                               f"duration: {span.duration_ms} ms<extra></extra>"),
            ))
            anchor = span.end_ts
        else:
            fig.add_annotation(x=anchor, y=span.label, text=f"⏭ {span.status.value}", showarrow=False,
                               xanchor="left", font={"color": STATUS_COLORS[span.status.value]})

    for highlighted in (False, True):
        chosen = [e for e in events if (e.event_id in highlight_refs) == highlighted]
        if not chosen:
            continue
        fig.add_trace(go.Scatter(
            x=[e.ts for e in chosen], y=[PHASE_LABELS[e.phase] for e in chosen], mode="markers",
            marker={"size": 14 if highlighted else 7, "color": HIGHLIGHT if highlighted else EVENT_COLOR,
                    "line": {"width": 2 if highlighted else 0, "color": "white"}, "symbol": "diamond"},
            customdata=[[e.event_id, e.type.value, _attrs(e)] for e in chosen],
            hovertemplate="%{customdata[0]} · %{customdata[1]}<br>%{customdata[2]}<extra></extra>",
            name="event (đang truy vết)" if highlighted else "trace event", showlegend=highlighted,
        ))

    fig.update_yaxes(categoryorder="array", categoryarray=labels[::-1], title=None)
    fig.update_xaxes(type="date", title=None)
    if zoom_setup:
        media = next((p for p in phases if p.phase == Phase.MEDIA), None)
        setup_end = media.established_ts if media is not None and media.established_ts is not None else None
        if setup_end is None:
            ends = [p.end_ts for p in phases if p.end_ts is not None]
            setup_end = max(ends) if ends else None
        starts = [p.start_ts for p in phases if p.start_ts is not None]
        if starts and setup_end is not None:
            fig.update_xaxes(range=[min(starts) - ZOOM_PAD / 4, setup_end + ZOOM_PAD])
    fig.update_layout(height=320, barmode="overlay", margin={"l": 10, "r": 10, "t": 10, "b": 10},
                      legend={"orientation": "h", "y": -0.2})
    return fig


def metric_panels(
    df: pd.DataFrame, anomalies: AnomalyResult, facts: Sequence[Fact], highlight: dict | None = None,
) -> go.Figure:
    """Stacked time series with baseline, absolute threshold, incident shading and trace highlights."""
    highlight = highlight or {}
    refs, fact_ids = set(highlight.get("refs", ())), set(highlight.get("fact_ids", ()))
    fig = make_subplots(rows=len(PANELS), cols=1, shared_xaxes=True, vertical_spacing=0.035,
                        subplot_titles=[title for title, _ in PANELS])
    baselines = {(b.source, b.metric.value): b for b in anomalies.baselines}
    rows = {(source, metric): row for row, (_, series) in enumerate(PANELS, start=1) for source, metric, _ in series}

    for row, (_, series) in enumerate(PANELS, start=1):
        thresholds: set[float] = set()
        for source, metric, dash in series:
            data = df[(df.source == source) & (df.metric == metric)].sort_values("t")
            if data.empty:
                continue
            label = f"{config.METRIC_META[metric]['label']} ({source})"
            if data.value.isna().all():
                suffix = "" if row == 1 else str(row)
                fig.add_annotation(text=f"{label}: không có dữ liệu ({len(data)} sample null)",
                                   xref=f"x{suffix} domain", yref=f"y{suffix} domain", x=0.5, y=0.5,
                                   showarrow=False, font={"color": STATUS_COLORS["failed"]})
                continue
            fig.add_trace(go.Scatter(
                x=data.ts, y=data.value, mode="lines", name=label, line={"dash": dash, "width": 1.6},
                customdata=data.sample_id, hovertemplate=f"{label}: %{{y}}<br>%{{customdata}}<extra></extra>",
            ), row=row, col=1)
            baseline = baselines.get((source, metric))
            if baseline is not None and baseline.median is not None:
                fig.add_hline(y=baseline.median, line_dash="dash", line_color=BASELINE_COLOR, line_width=1, row=row, col=1)
            thresholds.add(config.METRIC_RULES[metric]["abs"])
        for threshold in thresholds:
            fig.add_hline(y=threshold, line_dash="dot", line_color=STATUS_COLORS["failed"], line_width=1, row=row, col=1)

    for incident in anomalies.incidents:
        fig.add_vrect(x0=incident.start_ts, x1=incident.end_ts, fillcolor=INCIDENT_FILL, line_width=0, row="all", col=1)
    for anomaly in anomalies.anomalies:
        if anomaly.category == MetricCategory.RESOURCE and (anomaly.source, anomaly.metric.value) in rows:
            fig.add_vrect(x0=anomaly.start_ts, x1=anomaly.end_ts, fillcolor=RESOURCE_FILL, line_width=0,
                          row=rows[(anomaly.source, anomaly.metric.value)], col=1)

    traced = [fact for fact in facts if fact.fact_id in fact_ids]
    # One outline per merged span: an inference cites many overlapping windows.
    for start, end in _merge_windows([(f.window_start, f.window_end) for f in traced
                                      if f.window_start is not None and f.window_end is not None]):
        fig.add_vrect(x0=start, x1=end, fillcolor="rgba(0,0,0,0)", line={"color": HIGHLIGHT, "width": 2}, row="all", col=1)
    for fact in traced:
        if (fact.window_start is None or fact.window_end is None) and fact.ts is not None:
            fig.add_vline(x=fact.ts, line_color=HIGHLIGHT, line_width=1.5, line_dash="dot", row="all", col=1)
    hits = df[df.sample_id.isin(refs) & df.value.notna()]
    for (source, metric), group in hits.groupby(["source", "metric"]):
        if (source, metric) in rows:
            fig.add_trace(go.Scatter(
                x=group.ts, y=group.value, mode="markers", name="sample (đang truy vết)", showlegend=False,
                marker={"size": 12, "color": HIGHLIGHT, "line": {"width": 2, "color": "white"}},
                customdata=group.sample_id, hovertemplate="%{customdata}: %{y}<extra></extra>",
            ), row=rows[(source, metric)], col=1)

    fig.update_layout(height=860, hovermode="x unified", margin={"l": 10, "r": 10, "t": 30, "b": 10},
                      legend={"orientation": "h", "y": -0.05})
    return fig


def _merge_windows(windows: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    merged: list[tuple[datetime, datetime]] = []
    for start, end in sorted(windows):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _attrs(event: TraceEvent) -> str:
    return ", ".join(f"{key}={value}" for key, value in event.attrs.items()) or "—"
