"""QoS: ngưỡng cảnh báo, công thức MOS (ITU-T G.107 E-model rút gọn), bộ sinh metric."""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta

from callops.models import Impairment, MediaPath, NetworkCondition, QoSSample, Severity


@dataclass(frozen=True)
class Threshold:
    warning: float
    critical: float
    higher_is_worse: bool = True

    def classify(self, value: float) -> Severity:
        if self.higher_is_worse:
            if value >= self.critical:
                return Severity.CRITICAL
            if value >= self.warning:
                return Severity.WARNING
        else:
            if value <= self.critical:
                return Severity.CRITICAL
            if value <= self.warning:
                return Severity.WARNING
        return Severity.OK


# Ngưỡng tham khảo phổ biến cho thoại/video real-time:
# - RTT: ITU-T G.114 khuyến nghị one-way < 150ms  => RTT ~300ms là bắt đầu khó chịu.
# - Jitter > 30ms bắt đầu làm jitter buffer phải giãn, > 50ms gây méo/trễ rõ.
# - Packet loss > 1% bắt đầu nghe được (dù có PLC), > 5% chất lượng kém rõ rệt.
# - MOS: >= 4.0 tốt, < 3.6 nhiều người không hài lòng, < 3.1 kém.
THRESHOLDS: dict[str, Threshold] = {
    "rtt_ms": Threshold(warning=300, critical=500),
    "jitter_ms": Threshold(warning=30, critical=50),
    "packet_loss_pct": Threshold(warning=1.0, critical=5.0),
    "mos": Threshold(warning=3.6, critical=3.1, higher_is_worse=False),
    "concealment_pct": Threshold(warning=5.0, critical=10.0),
}

# Độ trễ phụ thêm theo đường media (hop thêm qua server)
PATH_EXTRA_RTT_MS: dict[MediaPath, float] = {
    MediaPath.P2P_HOST: -40.0,
    MediaPath.P2P_STUN: 0.0,
    MediaPath.TURN_RELAY: 45.0,
    MediaPath.SFU: 20.0,
}


def compute_mos(rtt_ms: float, jitter_ms: float, loss_pct: float) -> float:
    """E-model rút gọn (Cole & Rosenbluth) cho codec kiểu G.711 có PLC.

    R = 93.2 - Id - Ie_eff
      Id     : suy giảm do trễ.  d = one-way delay hiệu dụng = RTT/2 + 2*jitter + 10ms (codec)
      Ie_eff : suy giảm do mất gói. Ie=0, Bpl=25.1 (G.711 + PLC), BurstR=1 (mất ngẫu nhiên)
    MOS = 1 + 0.035R + 7e-6 * R(R-60)(100-R), kẹp trong [1.0, 4.5]
    """
    d = rtt_ms / 2 + 2 * jitter_ms + 10.0
    i_d = 0.024 * d + (0.11 * (d - 177.3) if d > 177.3 else 0.0)
    ie, bpl = 0.0, 25.1
    ie_eff = ie + (95 - ie) * loss_pct / (loss_pct + bpl)
    r = 93.2 - i_d - ie_eff
    if r <= 0:
        return 1.0
    if r >= 100:
        return 4.5
    mos = 1 + 0.035 * r + 7e-6 * r * (r - 60) * (100 - r)
    return round(max(1.0, min(4.5, mos)), 2)


class QoSGenerator:
    """Sinh metric mỗi giây cho 1 participant từ NetworkCondition + đường media + sự cố."""

    def __init__(self, rng: random.Random) -> None:
        self._rng = rng

    def sample(
        self,
        *,
        call_id: str,
        participant_id: str,
        t_s: int,
        start: datetime,
        network: NetworkCondition,
        path: MediaPath,
        impairments: list[Impairment],
    ) -> QoSSample:
        rtt = network.base_rtt_ms + PATH_EXTRA_RTT_MS[path]
        jitter = network.jitter_ms
        loss = network.loss_pct
        for imp in impairments:
            if imp.participant_id == participant_id and imp.start_s <= t_s < imp.end_s:
                rtt += imp.extra_rtt_ms
                jitter += imp.extra_jitter_ms
                loss += imp.extra_loss_pct

        g = self._rng.gauss
        rtt = max(5.0, g(rtt, rtt * 0.05))
        jitter = max(0.5, g(jitter, jitter * 0.15))
        loss = max(0.0, g(loss, loss * 0.2))

        # Video freeze xảy ra khi mất gói nặng (mất keyframe/NACK không kịp)
        freeze_prob = 0.0 if loss < 3 else min(0.9, (loss - 3) / 6)
        freezes = 1 if self._rng.random() < freeze_prob else 0
        # Concealment: % mẫu audio phải "bịa" ra bởi PLC (loss + gói đến trễ do jitter)
        concealment = min(100.0, loss * 1.3 + max(0.0, jitter - 30) * 0.15)

        return QoSSample(
            ts=start + timedelta(seconds=t_s),
            call_id=call_id,
            participant_id=participant_id,
            t_s=t_s,
            rtt_ms=round(rtt, 1),
            jitter_ms=round(jitter, 1),
            packet_loss_pct=round(loss, 2),
            mos=compute_mos(rtt, jitter, loss),
            video_freeze_count=freezes,
            concealment_pct=round(concealment, 2),
        )
