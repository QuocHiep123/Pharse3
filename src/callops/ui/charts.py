"""Biểu đồ QoS timeline (Plotly): 4 metric xếp dọc, ngưỡng, vùng sự cố, con trỏ thời gian."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from callops.diagnosis import Window
from callops.models import QoSSample, Severity
from callops.qos import THRESHOLDS, Threshold

__all__ = ["METRICS", "qos_figure"]

METRICS: tuple[tuple[str, str], ...] = (
    ("rtt_ms", "RTT (ms)"),
    ("jitter_ms", "Jitter (ms)"),
    ("packet_loss_pct", "Packet loss (%)"),
    ("mos", "MOS"),
)

_UNITS = {"rtt_ms": " ms", "jitter_ms": " ms", "packet_loss_pct": " %", "mos": ""}
# Palette categorical (Okabe-Ito, an toàn mù màu), gán theo thứ tự cố định của participant
_PALETTE = ("#0072B2", "#E69F00", "#009E73", "#CC79A7", "#56B4E9", "#D55E00", "#F0E442", "#7F7F7F")
_WARN_COLOR = "#B7791F"
_CRIT_COLOR = "#C0392B"
_SEVERITY_FILL = {Severity.WARNING: "#E69F00", Severity.CRITICAL: "#C0392B"}


def qos_figure(
    samples: Sequence[QoSSample],
    thresholds: Mapping[str, Threshold] = THRESHOLDS,
    windows: Sequence[Window] = (),
    *,
    t0: datetime | None = None,
    cursor_t: float | None = None,
) -> go.Figure:
    """Dựng figure 4 hàng (RTT/jitter/loss/MOS); x = giây kể từ t0."""
    if not samples:
        fig = go.Figure()
        fig.add_annotation(
            text="Không có dữ liệu QoS (cuộc gọi không thiết lập được media)",
            xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
        )
        fig.update_layout(template="plotly_white", xaxis={"visible": False}, yaxis={"visible": False})
        return fig

    base = t0 or min(s.ts for s in samples)
    participants = sorted({s.participant_id for s in samples})
    color = {p: _PALETTE[i % len(_PALETTE)] for i, p in enumerate(participants)}
    by_p = {p: sorted((s for s in samples if s.participant_id == p), key=lambda s: s.ts) for p in participants}

    fig = make_subplots(
        rows=len(METRICS), cols=1, shared_xaxes=True,
        subplot_titles=[label for _, label in METRICS], vertical_spacing=0.06,
    )
    for row, (metric, label) in enumerate(METRICS, start=1):
        for p in participants:
            ps = by_p[p]
            fig.add_trace(
                go.Scatter(
                    x=[(s.ts - base).total_seconds() for s in ps],
                    y=[getattr(s, metric) for s in ps],
                    mode="lines", name=p, legendgroup=p, showlegend=(row == 1),
                    line={"color": color[p], "width": 2},
                    hovertemplate=f"{p}: %{{y:.2f}}{_UNITS[metric]}<extra></extra>",
                ),
                row=row, col=1,
            )
        th = thresholds.get(metric)
        if th is not None:
            fig.add_hline(y=th.warning, row=row, col=1, line={"dash": "dash", "color": _WARN_COLOR, "width": 1},
                          annotation_text="warn", annotation_position="top right",
                          annotation_font_color=_WARN_COLOR)
            fig.add_hline(y=th.critical, row=row, col=1, line={"dash": "dash", "color": _CRIT_COLOR, "width": 1},
                          annotation_text="crit", annotation_position="top right",
                          annotation_font_color=_CRIT_COLOR)

    row_of = {m: i for i, (m, _) in enumerate(METRICS, start=1)}
    for w in windows:
        ps = by_p.get(w.participant)
        if w.metric not in row_of or not ps:
            continue
        first = ps[0]
        media_start = (first.ts - base).total_seconds() - first.t_s
        fig.add_vrect(
            x0=media_start + w.start_s, x1=media_start + w.end_s + 1,
            fillcolor=_SEVERITY_FILL.get(w.severity, _WARN_COLOR), opacity=0.15, line_width=0,
            annotation_text=w.fact_id, annotation_position="top left",
            row=row_of[w.metric], col=1,
        )

    if cursor_t is not None:
        fig.add_vline(x=cursor_t, row="all", col=1, line={"color": "#444444", "width": 1})

    fig.update_layout(
        template="plotly_white", height=820, hovermode="x unified",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.04, "x": 0},
        margin={"t": 90},
    )
    fig.update_xaxes(title_text="giây kể từ bắt đầu cuộc gọi", row=len(METRICS), col=1)
    return fig
