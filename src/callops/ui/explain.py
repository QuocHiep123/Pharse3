"""Glossary tiếng Việt + giải thích rule/verdict/metric cho demo UI.

Module thuần dữ liệu/hàm, không import gì của `callops.ui`. Số ngưỡng luôn lấy từ `THRESHOLDS`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from callops.models import MediaPath, Severity
from callops.qos import THRESHOLDS


@dataclass(frozen=True)
class Term:
    key: str
    name: str
    short_vi: str
    long_vi: str
    aliases: tuple[str, ...] = ()


def _t(key: str, name: str, short: str, long: str, *aliases: str) -> tuple[str, Term]:
    return key, Term(key, name, short, long, tuple(aliases))


GLOSSARY: dict[str, Term] = dict([
    _t("ICE", "ICE", "Quy trình tìm đường kết nối media giữa hai đầu.",
       "Interactive Connectivity Establishment: mỗi bên thu thập candidate (host/srflx/relay), trao đổi qua "
       "signaling rồi thử từng cặp (connectivity check) để chọn cặp đi được. Không cặp nào thành công thì "
       "cuộc gọi thất bại (ICE failed)."),
    _t("STUN", "STUN", "Server giúp client biết địa chỉ IP:port public của mình.",
       "Client gửi request tới STUN server và nhận lại địa chỉ public (server-reflexive) để dùng làm candidate "
       "srflx. STUN chỉ giúp xuyên NAT dạng cone; không chuyển tiếp media."),
    _t("TURN", "TURN", "Server chuyển tiếp media khi hai đầu không nối trực tiếp được.",
       "Khi NAT đối xứng hoặc firewall chặn UDP, media đi vòng qua TURN server (candidate relay). Đổi lại "
       "RTT tăng thêm và tốn CPU/RAM/băng thông của TURN."),
    _t("SFU", "SFU", "Server nhận một luồng từ mỗi người rồi chuyển tiếp cho cả phòng.",
       "Selective Forwarding Unit dùng cho gọi nhóm (hơn 2 người): mỗi participant chỉ nối tới SFU. Lỗi có "
       "thể chỉ nằm ở đường mạng riêng của một participant chứ không phải SFU."),
    _t("NAT", "NAT", "Thiết bị đổi địa chỉ nội bộ sang địa chỉ public khi ra Internet.",
       "Network Address Translation làm máy sau router không có IP public, nên cần STUN/ICE để hai đầu "
       "tìm được nhau. Kiểu NAT quyết định có xuyên được trực tiếp hay phải qua TURN."),
    _t("SYMMETRIC_NAT", "Symmetric NAT", "NAT đổi port theo từng đích nên srflx vô dụng với peer.",
       "Với NAT đối xứng, mapping thay đổi theo địa chỉ đích nên địa chỉ học từ STUN không dùng được cho "
       "peer. Hai đầu cùng bị như vậy mà không có TURN thì ICE thất bại.",
       "NAT đối xứng", "SYMMETRIC"),
    _t("SDP", "SDP", "Bản mô tả phiên media (codec, địa chỉ, khóa) trao đổi qua offer/answer.",
       "Session Description Protocol: bên gọi gửi offer, bên nhận trả answer; hai bên thống nhất codec, "
       "candidate và tham số DTLS trước khi chạy ICE."),
    _t("SIGNALING", "Signaling", "Kênh báo hiệu để thiết lập, thay đổi và kết thúc cuộc gọi.",
       "WebRTC không quy định signaling; ứng dụng tự dùng WebSocket/HTTP để chuyển SDP và ICE candidate "
       "(INVITE/JOIN_ROOM, BYE). Signaling không mang media."),
    _t("CANDIDATE", "Candidate", "Một địa chỉ IP:port mà đầu cuối có thể dùng để nhận media.",
       "Có ba loại: host (IP local), srflx (public, học từ STUN) và relay (cấp phát trên TURN). ICE ghép "
       "candidate hai phía thành các cặp để kiểm tra."),
    _t("HOST", "Host candidate", "Candidate dùng IP local của máy.",
       "Dùng được khi hai bên cùng LAN; đường P2P_HOST có RTT thấp nhất."),
    _t("SRFLX", "Srflx candidate", "Candidate là địa chỉ public học được từ STUN.",
       "Server-reflexive: dùng để P2P xuyên NAT dạng cone. Với NAT đối xứng thường không dùng được.",
       "server-reflexive"),
    _t("RELAY", "Relay candidate", "Candidate là địa chỉ cấp phát trên TURN server.",
       "Chọn khi không còn cặp P2P nào đi được; media đi qua TURN nên chậm hơn nhưng gần như luôn kết nối được."),
    _t("DTLS_SRTP", "DTLS-SRTP", "Cơ chế bắt tay khóa và mã hóa media của WebRTC.",
       "DTLS bắt tay để thống nhất khóa, SRTP dùng khóa đó mã hóa gói RTP. Sau bước này media được "
       "thiết lập (MEDIA ESTABLISHED) và getStats bắt đầu có số liệu.", "DTLS", "SRTP"),
    _t("RTT", "RTT", "Thời gian khứ hồi của gói tin (ms).",
       "Round-trip time. Tăng khi đi relay/đường xa hoặc hàng đợi đầy. ITU-T G.114 khuyến nghị "
       "độ trễ một chiều dưới 150 ms."),
    _t("JITTER", "Jitter", "Độ dao động thời gian đến của các gói (ms).",
       "Jitter cao làm jitter buffer phải giãn ra, tăng trễ hoặc gây méo tiếng/giật hình."),
    _t("PACKET_LOSS", "Packet loss", "Tỷ lệ gói tin bị mất (%).",
       "Mất gói làm thiếu dữ liệu audio/video; PLC che được một phần. Loss đi cùng RTT/jitter tăng gợi ý "
       "nghẽn mạng, loss đơn lẻ gợi ý lỗi vô tuyến.", "loss", "mất gói"),
    _t("MOS", "MOS", "Điểm chất lượng cảm nhận (1.0 đến 4.5) tính từ RTT/jitter/loss.",
       "Mean Opinion Score theo E-model rút gọn. MOS thấp là triệu chứng QoE; nguyên nhân nằm ở "
       "các metric mạng hoặc log."),
    _t("CONCEALMENT", "Concealment", "Tỷ lệ audio do PLC tự sinh ra để bù gói mất (%).",
       "Packet Loss Concealment 'bịa' mẫu âm thanh khi mất gói. Tỷ lệ cao nghĩa là người nghe nghe "
       "nhiều đoạn không phải tiếng thật.", "PLC"),
    _t("BUFFERBLOAT", "Bufferbloat", "Hàng đợi router quá đầy gây trễ rồi mất gói.",
       "Gói chờ lâu trong hàng đợi (RTT/jitter tăng) rồi bị drop (loss tăng). Thường do uplink bị "
       "chiếm hết băng thông."),
    _t("FEC", "FEC", "Gửi thêm dữ liệu dự phòng để khôi phục gói mất mà không cần gửi lại.",
       "Forward Error Correction (Opus in-band FEC, RED/ULPFEC) giảm ảnh hưởng của loss ngẫu nhiên "
       "với giá là tốn thêm băng thông."),
    _t("SIMULCAST", "Simulcast", "Gửi nhiều layer chất lượng để SFU chọn layer phù hợp cho từng người nhận.",
       "Người có mạng yếu nhận layer thấp, không kéo chất lượng cả phòng xuống.", "SVC"),
    _t("FACT", "FACT", "Dữ kiện quan sát trực tiếp từ log hoặc metric, có id dạng [F03].",
       "FACT chỉ ghi lại điều đã đo/đã log, không suy diễn. Mọi INFERENCE phải trích dẫn FACT id."),
    _t("INFERENCE", "INFERENCE", "Giả thuyết suy ra từ FACT, luôn kèm id FACT làm bằng chứng.",
       "INFERENCE là suy luận (có độ tin cậy) chứ không phải sự thật; phải trích dẫn các FACT mà nó dựa vào."),
])


def _patterns(term: Term) -> list[str]:
    seen: dict[str, None] = {}
    for s in (term.name, term.key, *term.aliases):
        if s:
            seen[s] = None
    return list(seen)


def find_terms(text: str) -> list[Term]:
    """Tìm thuật ngữ trong text (không phân biệt hoa thường), trả theo vị trí đầu tiên, không trùng."""
    if not text:
        return []
    spans: list[tuple[int, int, Term]] = []
    for term in GLOSSARY.values():
        for pat in _patterns(term):
            rx = re.compile(r"(?<!\w)" + re.escape(pat) + r"(?!\w)", re.IGNORECASE)
            spans += [(m.start(), m.end(), term) for m in rx.finditer(text)]
    # Chuỗi dài hơn thắng khi chồng nhau
    accepted: list[tuple[int, int, Term]] = []
    for s, e, term in sorted(spans, key=lambda x: (-(x[1] - x[0]), x[0])):
        if all(e <= a or s >= b for a, b, _ in accepted):
            accepted.append((s, e, term))
    first: dict[str, tuple[int, Term]] = {}
    for s, _, term in sorted(accepted, key=lambda x: x[0]):
        first.setdefault(term.key, (s, term))
    return [t for _, t in sorted(first.values(), key=lambda x: x[0])]


def glossary_markdown(keys: Iterable[str] | None = None) -> str:
    """Danh sách markdown '**name** — short_vi'; None = toàn bộ."""
    terms = GLOSSARY.values() if keys is None else [GLOSSARY[k] for k in keys if k in GLOSSARY]
    return "\n".join(f"- **{t.name}** — {t.short_vi}" for t in terms)


@dataclass(frozen=True)
class RuleExplain:
    title_vi: str
    when_vi: str  # điều kiện tiên quyết để rule khớp (dùng làm "lý do không khớp")


RULE_EXPLAIN: dict[str, RuleExplain] = {
    "ice_failure_root_cause": RuleExplain(
        "Nguyên nhân ICE thất bại",
        "Cần FACT log ICE_FAILED (không cặp candidate nào kết nối được). Cuộc gọi không có media."),
    "turn_fallback_explained": RuleExplain(
        "Giải thích việc fallback sang TURN",
        "Cần FACT log TURN_FALLBACK (P2P không đi được nên media chuyển sang relay)."),
    "congestion_vs_random_loss": RuleExplain(
        "Phân biệt nghẽn mạng và mất gói ngẫu nhiên",
        "Cần ít nhất một đoạn packet_loss_pct vượt ngưỡng. Loss trùng thời gian với jitter/RTT vượt "
        "ngưỡng thì là nghẽn, ngược lại là mất gói ngẫu nhiên."),
    "latency_only": RuleExplain(
        "Trễ cao nhưng không mất gói",
        "Cần đoạn rtt_ms vượt ngưỡng ở participant mà participant đó không có đoạn packet_loss_pct "
        "vượt ngưỡng nào."),
    "qoe_impact": RuleExplain(
        "Ảnh hưởng tới chất lượng người dùng cảm nhận (QoE)",
        "Cần đoạn mos hoặc concealment_pct vượt ngưỡng ở một participant; các vi phạm QoS khác "
        "của participant đó được dùng làm nguyên nhân."),
    "sfu_isolated_participant": RuleExplain(
        "Sự cố cô lập ở một participant qua SFU",
        "Cuộc gọi phải đi qua SFU và chỉ một phần participant có vi phạm CRITICAL (không phải tất cả, "
        "cũng không phải không ai)."),
    "healthy_call": RuleExplain(
        "Cuộc gọi khỏe mạnh",
        "Không có đoạn nào vượt ngưỡng và không có log ICE_FAILED hoặc CALL_FAILED."),
}


def rule_explain(name: str) -> RuleExplain:
    return RULE_EXPLAIN.get(name) or RuleExplain(title_vi=name, when_vi="(chưa có mô tả cho rule này)")


VERDICT_EXPLAIN_VI: dict[Severity, str] = {
    Severity.OK: "OK: không metric nào vượt ngưỡng và cuộc gọi kết nối bình thường.",
    Severity.WARNING: "WARNING: có metric vượt ngưỡng cảnh báo; người dùng có thể thấy giảm chất lượng nhưng cuộc gọi vẫn chạy.",
    Severity.CRITICAL: "CRITICAL: cuộc gọi thất bại hoặc có metric vượt ngưỡng nghiêm trọng, cần xử lý.",
}

MEDIA_PATH_EXPLAIN_VI: dict[MediaPath, str] = {
    MediaPath.P2P_HOST: "P2P_HOST: hai bên cùng LAN, nối trực tiếp bằng IP local nên RTT thấp nhất.",
    MediaPath.P2P_STUN: "P2P_STUN: xuyên NAT nhờ STUN (srflx tới srflx), media đi thẳng giữa hai đầu; đường bình thường.",
    MediaPath.TURN_RELAY: "TURN_RELAY: P2P không đi được (NAT đối xứng/firewall chặn UDP) nên media đi vòng qua TURN; RTT tăng và phụ thuộc tải TURN server.",
    MediaPath.SFU: "SFU: gọi nhóm, mỗi người nối tới SFU và SFU chuyển tiếp; lỗi có thể chỉ ở đường mạng riêng của một participant.",
}

NO_MEDIA_PATH_EXPLAIN_VI = (
    "Không có media path: ICE thất bại nên không thiết lập được kết nối, cuộc gọi không có media."
)

_METRIC_LABEL_VI: dict[str, tuple[str, str]] = {
    "rtt_ms": ("RTT", "thời gian khứ hồi của gói (ms)"),
    "jitter_ms": ("Jitter", "độ dao động thời gian đến của gói (ms)"),
    "packet_loss_pct": ("Packet loss", "tỷ lệ gói mất (%)"),
    "mos": ("MOS", "điểm chất lượng cảm nhận, thang 1.0 đến 4.5"),
    "concealment_pct": ("Concealment", "tỷ lệ audio do PLC che gói mất (%)"),
}


def metric_explain_vi(metric: str) -> str:
    """Giải thích metric kèm ngưỡng lấy từ THRESHOLDS."""
    if metric not in THRESHOLDS:
        raise ValueError(f"Metric lạ: {metric!r}")
    th = THRESHOLDS[metric]
    label, desc = _METRIC_LABEL_VI.get(metric, (metric, ""))
    w, c = f"{th.warning:g}", f"{th.critical:g}"
    if th.higher_is_worse:
        rule = f"càng cao càng xấu: cảnh báo khi ≥ {w}, nghiêm trọng khi ≥ {c}"
    else:
        rule = f"càng thấp càng xấu: cảnh báo khi ≤ {w}, nghiêm trọng khi ≤ {c}"
    text = f"{label} là {desc}; {rule}."
    if metric == "mos":
        text += " MOS là hệ quả của RTT/jitter/loss, nên MOS thấp là triệu chứng, cần tìm nguyên nhân ở metric mạng."
    return text
