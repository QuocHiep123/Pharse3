"""Timeline các bước call flow + SVG sequence diagram (CSS animation, không JS)."""

from __future__ import annotations

from datetime import datetime
from html import escape
from typing import Sequence

from callops.models import CallEvent, CallState
from callops.ui.contracts import STEP_TITLES_VI, FlowStep

__all__ = ["FlowStep", "INFRA_ACTORS", "EVENT_INFO", "build_timeline", "actors_of", "steps_until",
           "render_flow_svg"]

INFRA_ACTORS: tuple[str, ...] = ("Signaling", "STUN", "TURN", "SFU")

# event -> (step_no, tiêu đề tiếng Việt, giải thích cho người mới)
EVENT_INFO: dict[str, tuple[int, str, str]] = {
    "INVITE": (1, "INVITE cuộc gọi",
               "Caller báo cho signaling server rằng muốn gọi tới callee. Lúc này chưa có kết nối media nào."),
    "JOIN_ROOM": (1, "Vào phòng gọi nhóm",
                  "Người tham gia xin vào phòng qua signaling server. Gọi nhóm dùng SFU nên không có luồng P2P trực tiếp."),
    "RINGING_ACCEPTED": (1, "Callee chấp nhận",
                         "Callee đổ chuông và đồng ý nhận cuộc gọi; signaling server chuyển tin này về caller."),
    "SDP_OFFER": (2, "SDP offer",
                  "Caller mô tả mình muốn gửi gì (codec opus/VP8, BUNDLE) trong SDP và gửi qua signaling server; "
                  "chưa có media nào chảy."),
    "SDP_ANSWER": (2, "SDP answer",
                   "Callee trả lời bằng SDP answer để chốt codec hai bên cùng hỗ trợ. Sau bước này hai bên đã thống nhất định dạng media."),
    "STUN_TIMEOUT": (3, "STUN timeout",
                     "Máy gửi STUN Binding Request để biết IP public nhưng không nhận được phản hồi, thường do firewall chặn UDP. "
                     "Sẽ không có srflx candidate."),
    "ICE_GATHERING_COMPLETE": (3, "Thu thập ICE candidate xong",
                               "Trình duyệt gom các địa chỉ có thể dùng: host (IP local), srflx (IP public học từ STUN) "
                               "và relay (cấp phát trên TURN)."),
    "ICE_CANDIDATES_EXCHANGED": (4, "Trao đổi ICE candidate",
                                 "Hai bên gửi danh sách candidate cho nhau qua signaling (trickle ICE) để chuẩn bị thử kết nối."),
    "TURN_FALLBACK": (4, "Fallback sang TURN",
                      "Không đi trực tiếp được nên phải chuyển sang relay qua TURN server. Gọi được nhưng thêm độ trễ và tốn băng thông server."),
    "ICE_SELECTED_PAIR": (4, "Chọn cặp candidate",
                          "ICE đã thử các cặp candidate và chọn ra cặp thành công (nominated) để truyền media."),
    "ICE_FAILED": (4, "ICE thất bại",
                   "Không cặp candidate nào kết nối được. Nếu không có TURN làm đường dự phòng thì cuộc gọi không thể có media."),
    "SFU_CONNECTED": (4, "Kết nối SFU",
                      "Participant đã nối được tới SFU. SFU nhận một luồng từ mỗi người rồi forward cho những người còn lại."),
    "MEDIA_ESTABLISHED": (5, "Media bắt đầu chảy",
                          "DTLS handshake xong, SRTP audio/video bắt đầu truyền. Từ đây hệ thống đo QoS mỗi giây."),
    "QOS_ALERT": (5, "Cảnh báo QoS",
                  "Một chỉ số chất lượng (RTT, jitter, packet loss, MOS...) vượt ngưỡng trong THRESHOLDS."),
    "QOS_RECOVERED": (5, "QoS hồi phục",
                      "Chỉ số từng vượt ngưỡng đã quay về mức bình thường."),
    "BYE": (6, "BYE - kết thúc",
            "Một bên gửi BYE, hai bên đóng PeerConnection và giải phóng tài nguyên như TURN allocation."),
    "CALL_FAILED": (6, "Cuộc gọi thất bại",
                    "Không thiết lập được media nên cuộc gọi bị đóng với lỗi."),
}

_STATE_STEP: dict[CallState, int] = {
    CallState.IDLE: 1, CallState.SETUP: 1, CallState.OFFER_SENT: 2, CallState.ANSWER_RECEIVED: 2,
    CallState.ICE_CHECKING: 4, CallState.CONNECTED: 5, CallState.TERMINATED: 6, CallState.FAILED: 6,
}
_UNKNOWN_EXPLAIN = "Sự kiện ngoài danh sách chuẩn; xem nội dung log gốc để biết chi tiết."


def build_timeline(events: Sequence[CallEvent], t0: datetime | None = None) -> list[FlowStep]:
    """Dựng danh sách mũi tên (FlowStep) từ CallEvent, sort theo ts."""
    evs = sorted(events, key=lambda e: e.ts)
    if not evs:
        return []
    base = t0 or evs[0].ts

    caller, callees = "Caller", []
    for e in evs:
        if e.event in ("INVITE", "JOIN_ROOM") and e.detail.get("caller"):
            caller = str(e.detail["caller"])
            break
    for e in evs:
        if e.event == "RINGING_ACCEPTED" and e.detail.get("callee"):
            callees.append(str(e.detail["callee"]))
    peer = callees[0] if callees else "Peer"

    media_target = peer
    steps: list[FlowStep] = []
    for i, e in enumerate(evs, start=1):
        d = e.detail
        p = str(d.get("participant", caller))
        ev = e.event
        if ev in ("INVITE", "JOIN_ROOM", "SDP_OFFER", "ICE_CANDIDATES_EXCHANGED", "BYE", "CALL_FAILED"):
            a, b = caller, "Signaling"
        elif ev == "RINGING_ACCEPTED":
            a, b = str(d.get("callee", peer)), "Signaling"
        elif ev == "SDP_ANSWER":
            a, b = "Signaling", caller
        elif ev == "STUN_TIMEOUT":
            a, b = p, "STUN"
        elif ev == "ICE_GATHERING_COMPLETE":
            types = d.get("candidate_types", "")
            types = ",".join(map(str, types)) if isinstance(types, (list, tuple)) else str(types)
            a, b = p, ("TURN" if "relay" in types else "STUN")
        elif ev == "TURN_FALLBACK":
            a, b = p, "TURN"
        elif ev == "SFU_CONNECTED":
            a, b = p, "SFU"
        elif ev == "ICE_FAILED":
            a, b = (p, "SFU") if "participant" in d else (caller, peer)
        elif ev in ("ICE_SELECTED_PAIR", "MEDIA_ESTABLISHED"):
            path = d.get("media_path")
            media_target = "SFU" if path == "SFU" else "TURN" if path == "TURN_RELAY" else peer
            a, b = caller, media_target
        elif ev in ("QOS_ALERT", "QOS_RECOVERED"):
            target = caller if p == peer and media_target == peer else media_target
            a, b = p, target
        else:
            a, b = caller, "Signaling"

        info = EVENT_INFO.get(ev)
        if info:
            step_no, title, explain = info
        else:
            step_no, title, explain = _STATE_STEP.get(e.state, 5), ev, _UNKNOWN_EXPLAIN
        steps.append(FlowStep(
            seq=i, step_no=step_no, t=(e.ts - base).total_seconds(), actor_from=a, actor_to=b,
            event=ev, title=title, message=e.message, explain_vi=explain,
            log_ref=f"{ev} @ {e.ts.isoformat()}", level=e.level,
        ))
    return steps


def actors_of(steps: Sequence[FlowStep]) -> list[str]:
    """Participant theo thứ tự xuất hiện, rồi các hạ tầng có dùng."""
    seen: list[str] = []
    for s in steps:
        for a in (s.actor_from, s.actor_to):
            if a not in INFRA_ACTORS and a not in seen:
                seen.append(a)
    used = {a for s in steps for a in (s.actor_from, s.actor_to)}
    return seen + [a for a in INFRA_ACTORS if a in used]


def steps_until(steps: Sequence[FlowStep], t: float) -> int:
    return sum(1 for s in steps if s.t <= t)


# ------------------------------------------------------------------ SVG
_COL_W, _LEFT, _TOP, _ROW_H, _BAND_H = 150, 80, 30, 54, 26

_CSS = """
.lane{stroke:currentColor;stroke-opacity:.3;stroke-dasharray:4 4}
.actor rect{fill:rgba(127,127,127,.15);stroke:currentColor;stroke-opacity:.5;rx:6}
.actor text,.lbl,.tm,.band text{fill:currentColor;font:12px sans-serif}
.actor text{font-weight:600;text-anchor:middle}
.tm{font-size:10px;opacity:.6}
.band rect{fill:rgba(99,102,241,.15)}
.band text{font-weight:600;font-size:11px}
.arrow{stroke:#3b82f6;fill:none;stroke-width:1.8}
.step.problem .arrow{stroke:#ef4444}
.step.problem .lbl{fill:#ef4444}
.step.current .arrow{stroke-dasharray:300;animation:callops-draw .8s ease-out forwards}
.step.current .lbl{animation:callops-blink 1.2s ease-in-out infinite;font-weight:700}
#callops-flow .head{fill:#3b82f6}
@keyframes callops-draw{from{stroke-dashoffset:300}to{stroke-dashoffset:0}}
@keyframes callops-blink{50%{opacity:.45}}
@media (prefers-reduced-motion:reduce){.step.current .arrow,.step.current .lbl{animation:none}}
"""


_VIEW_H = 600  # chiều cao cửa sổ nhìn; sơ đồ dài hơn thì cửa sổ trượt theo bước hiện tại


def _window_top(ys: Sequence[float], n: int, height: int) -> int:
    """y đầu cửa sổ nhìn sao cho bước hiện tại (bước thứ n) nằm gần đáy cửa sổ."""
    if height <= _VIEW_H or n == 0:
        return 0
    return int(max(0, min(ys[n - 1] + 60 - _VIEW_H, height - _VIEW_H)))


def render_flow_svg(steps: Sequence[FlowStep], upto: int | None = None) -> str:
    wrap_open = '<div class="callops-flow-wrap" style="max-height:620px;overflow:auto">'
    if not steps:
        return (f'{wrap_open}<svg id="callops-flow" xmlns="http://www.w3.org/2000/svg" width="320" height="50">'
                f'<text x="10" y="30" fill="currentColor" font-size="13">Không có sự kiện nào để hiển thị</text>'
                f'</svg></div>')

    n = len(steps) if upto is None else max(0, min(upto, len(steps)))
    actors = actors_of(steps)
    x_of = {a: _LEFT + i * _COL_W for i, a in enumerate(actors)}
    width = _LEFT * 2 + _COL_W * (len(actors) - 1)

    # layout cho toàn bộ bước để sơ đồ không "nhảy" khi tăng upto
    ys: list[float] = []
    bands: list[tuple[float, int]] = []
    y, prev_no = _TOP + 40, None
    for s in steps:
        if s.step_no != prev_no:
            bands.append((y, s.step_no))
            y += _BAND_H
            prev_no = s.step_no
        ys.append(y + 20)
        y += _ROW_H
    height = int(y + 20)
    view_h = min(height, _VIEW_H)
    top = _window_top(ys, n, height)
    head_y = _TOP - 6 if top == 0 else top + 4  # hàng actor luôn nằm ở đầu cửa sổ

    out = [wrap_open,
           f'<svg id="callops-flow" xmlns="http://www.w3.org/2000/svg" width="{width}" height="{view_h}" '
           f'viewBox="0 {top} {width} {view_h}" role="img" aria-label="Sequence diagram cuộc gọi">',
           f"<style>{_CSS}</style>",
           '<defs><marker id="callops-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
           'markerHeight="7" orient="auto-start-reverse"><path class="head" d="M0,0 L10,5 L0,10 z"/></marker></defs>']
    for a in actors:
        out.append(f'<line class="lane" x1="{x_of[a]}" y1="{_TOP + 24}" x2="{x_of[a]}" y2="{height - 10}"/>')

    last_seq = steps[n - 1].seq if n else None
    visible_idx = {i for i in range(n)}
    for by, no in bands:
        # chỉ hiện band khi bước đầu tiên của nhóm đã hiện
        first = next(i for i, s in enumerate(steps) if s.step_no == no)
        if first in visible_idx:
            title = STEP_TITLES_VI.get(no, "")
            out.append(f'<g class="band"><rect x="4" y="{by}" width="{width - 8}" height="{_BAND_H - 6}" rx="4"/>'
                       f'<text x="10" y="{by + 13}">{escape(f"STEP {no} · {title}")}</text></g>')

    for i in range(n):
        s, yy = steps[i], ys[i]
        x1, x2 = x_of[s.actor_from], x_of[s.actor_to]
        cls = "step" + (" problem" if s.is_problem else "") + (" current" if s.seq == last_seq else "")
        if x1 == x2:
            path = f"M{x1},{yy - 8} h40 v16 h-38"
            lx, anchor = x1 + 46, "start"
        else:
            path = f"M{x1},{yy} L{x2},{yy}"
            lx, anchor = (x1 + x2) / 2, "middle"
        out.append(
            f'<g class="{cls}" data-seq="{s.seq}"><title>{escape(s.log_ref)}</title>'
            f'<path class="arrow" d="{path}" marker-end="url(#callops-arrow)"/>'
            f'<text class="lbl" x="{lx}" y="{yy - 8 if x1 != x2 else yy + 4}" text-anchor="{anchor}">'
            f'{escape(f"{s.seq}. {s.title}")}</text>'
            f'<text class="tm" x="{lx}" y="{yy + 14}" text-anchor="{anchor}">+{s.t:.2f}s</text></g>')
    # hàng actor vẽ SAU CÙNG để các bước trượt qua không đè lên tên actor
    if top:
        out.append(f'<rect class="headbg" x="0" y="{top}" width="{width}" height="40" fill="Canvas" fill-opacity=".95"/>')
    for a in actors:
        x = x_of[a]
        out.append(f'<g class="actor"><rect x="{x - 55}" y="{head_y}" width="110" height="30"/>'
                   f'<text x="{x}" y="{head_y + 20}">{escape(a)}</text></g>')
    out.append("</svg></div>")
    return "".join(out)
