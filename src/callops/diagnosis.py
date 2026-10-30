"""AIOps diagnosis: tách bạch FACT và INFERENCE.

Pipeline:
  1. Đọc lại log sự kiện + metric QoS của cuộc gọi từ store (OpenSearch / in-memory).
  2. FactExtractor   : chỉ trích những gì CÓ trong dữ liệu (timestamp + dòng log/metric gốc làm evidence).
  3. InferenceEngine : các rule suy diễn; mỗi INFERENCE phải trỏ về FACT id cụ thể + nêu lập luận.
  4. DiagnosisReport : validator Pydantic từ chối INFERENCE trích dẫn FACT không tồn tại.
"""

from __future__ import annotations

import json
import logging
import statistics
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from callops.models import DiagnosisReport, Fact, Inference, MediaPath, QoSSample, Severity
from callops.qos import THRESHOLDS
from callops.storage import EVENTS_INDEX, QOS_INDEX, TelemetryStore

log = logging.getLogger("callops.aiops")

KEY_EVENTS = {"STUN_TIMEOUT", "ICE_GATHERING_COMPLETE", "TURN_FALLBACK", "ICE_SELECTED_PAIR", "ICE_FAILED",
              "CALL_FAILED", "MEDIA_ESTABLISHED", "SFU_CONNECTED"}
MERGE_GAP_S = 2  # gộp các đoạn vượt ngưỡng cách nhau <= 2s (tránh nhiễu dao động quanh ngưỡng)


@dataclass
class Window:
    """Đoạn thời gian 1 metric của 1 participant vượt ngưỡng (gắn với 1 FACT)."""

    fact_id: str
    participant: str
    metric: str
    severity: Severity
    start_s: int
    end_s: int
    peak: float

    def overlaps(self, other: "Window") -> bool:
        return self.start_s <= other.end_s and other.start_s <= self.end_s


@dataclass
class FactBundle:
    facts: list[Fact]
    windows: list[Window]
    events: list[dict[str, Any]]
    samples: list[QoSSample]

    def by_code(self, *codes: str) -> list[Fact]:
        return [f for f in self.facts if f.error_code in codes]

    def by_tag(self, *tags: str) -> list[Fact]:
        return [f for f in self.facts if all(t in f.tags for t in tags)]


# =========================================================================== FACT
class FactExtractor:
    def __init__(self) -> None:
        self._n = 0

    def _id(self) -> str:
        self._n += 1
        return f"F{self._n:02d}"

    def extract(self, events: list[dict[str, Any]], samples: list[QoSSample]) -> FactBundle:
        facts: list[Fact] = []
        log.info("FACT extraction: đọc %d log event + %d metric sample", len(events), len(samples))

        for ev in events:
            if ev["event"] not in KEY_EVENTS:
                continue
            d = ev.get("detail", {})
            tags = ["log", ev["event"].lower()]
            if "participant" in d:
                tags.append(d["participant"])
            if "candidate_types" in d:
                tags += [f"cand:{c}" for c in d["candidate_types"].split(",")]
            if "nat" in d:
                tags.append(f"nat:{d['nat']}")
            if "media_path" in d:
                tags.append(f"path:{d['media_path']}")
            f = Fact(id=self._id(), ts=ev["ts"], source="log", statement=ev["message"],
                     evidence=json.dumps({k: ev[k] for k in ("ts", "level", "event", "error_code", "detail")},
                                         ensure_ascii=False),
                     error_code=ev.get("error_code") or (ev["event"] if ev["level"] != "INFO" else None),
                     tags=tags)
            facts.append(f)
            log.debug("%s [log]    %s", f.id, f.statement)

        windows = self._threshold_windows(samples, facts)
        self._summaries(samples, facts)
        log.info("→ %d FACT (%d đoạn vượt ngưỡng)", len(facts), len(windows))
        return FactBundle(facts, windows, events, samples)

    def _threshold_windows(self, samples: list[QoSSample], facts: list[Fact]) -> list[Window]:
        windows: list[Window] = []
        pids = sorted({s.participant_id for s in samples})
        for pid in pids:
            ps = [s for s in samples if s.participant_id == pid]
            for metric, th in THRESHOLDS.items():
                bad = [s for s in ps if th.classify(getattr(s, metric)) != Severity.OK]
                groups: list[list[QoSSample]] = []
                for s in bad:
                    if groups and s.t_s - groups[-1][-1].t_s <= MERGE_GAP_S:
                        groups[-1].append(s)
                    else:
                        groups.append([s])
                for g in groups:
                    worst = (max if th.higher_is_worse else min)(g, key=lambda s: getattr(s, metric))
                    peak = getattr(worst, metric)
                    sev = th.classify(peak)
                    f = Fact(
                        id=self._id(), ts=g[0].ts, source="metric",
                        statement=(f"[{pid}] {metric} vượt ngưỡng {sev.value} từ t={g[0].t_s}s đến t={g[-1].t_s}s "
                                   f"({len(g)} mẫu), đỉnh={peak} (warn={th.warning}, crit={th.critical})"),
                        evidence=f"index={QOS_INDEX} worst_sample=" + worst.model_dump_json(),
                        error_code=f"QOS_{metric.upper()}_{sev.value}",
                        tags=["metric", "breach", pid, metric, sev.value],
                    )
                    facts.append(f)
                    windows.append(Window(f.id, pid, metric, sev, g[0].t_s, g[-1].t_s, peak))
                    log.debug("%s [metric] %s", f.id, f.statement)
        return windows

    def _summaries(self, samples: list[QoSSample], facts: list[Fact]) -> None:
        for pid in sorted({s.participant_id for s in samples}):
            ps = [s for s in samples if s.participant_id == pid]
            rtts = sorted(s.rtt_ms for s in ps)
            stats = {
                "samples": len(ps),
                "rtt_avg": round(statistics.fmean(rtts), 1),
                "rtt_p95": rtts[int(0.95 * (len(rtts) - 1))],
                "jitter_avg": round(statistics.fmean(s.jitter_ms for s in ps), 1),
                "loss_avg": round(statistics.fmean(s.packet_loss_pct for s in ps), 2),
                "mos_avg": round(statistics.fmean(s.mos for s in ps), 2),
                "mos_min": min(s.mos for s in ps),
                "freezes": sum(s.video_freeze_count for s in ps),
            }
            f = Fact(id=self._id(), ts=ps[0].ts, source="metric",
                     statement=f"[{pid}] tổng hợp {len(ps)}s: " + ", ".join(f"{k}={v}" for k, v in stats.items()),
                     evidence=f"aggregate over index={QOS_INDEX} participant={pid} " + json.dumps(stats),
                     tags=["metric", "summary", pid])
            facts.append(f)
            log.debug("%s [metric] %s", f.id, f.statement)


# ====================================================================== INFERENCE
Rule = Callable[[FactBundle], list[Inference]]


class InferenceEngine:
    def __init__(self) -> None:
        self._n = 0
        self.rules: list[tuple[str, Rule]] = [
            ("ice_failure_root_cause", self._ice_failure),
            ("turn_fallback_explained", self._turn_fallback),
            ("congestion_vs_random_loss", self._loss_pattern),
            ("latency_only", self._latency_only),
            ("qoe_impact", self._qoe_impact),
            ("sfu_isolated_participant", self._sfu_isolated),
            ("healthy_call", self._healthy),
        ]

    def _inf(self, **kw: Any) -> Inference:
        self._n += 1
        return Inference(id=f"I{self._n:02d}", **kw)

    def infer(self, b: FactBundle) -> list[Inference]:
        out: list[Inference] = []
        for name, rule in self.rules:
            res = rule(b)
            if res:
                for i in res:
                    log.info("rule %-26s ✔ %s: %s  (từ %s, conf=%.2f)", name, i.id, i.hypothesis,
                             ",".join(i.derived_from), i.confidence)
            else:
                log.debug("rule %-26s ✘ không khớp", name)
            out += res
        return out

    # ---- rules ---------------------------------------------------------
    def _ice_failure(self, b: FactBundle) -> list[Inference]:
        failed = b.by_code("ICE_FAILED")
        if not failed:
            return []
        gathering = b.by_tag("ice_gathering_complete")
        no_relay = [f for f in gathering if "cand:relay" not in f.tags]
        stun_to = b.by_code("STUN_TIMEOUT")
        hard_nat = [f for f in gathering if "nat:SYMMETRIC" in f.tags or "nat:UDP_BLOCKED" in f.tags]
        cited = failed + no_relay + stun_to + hard_nat
        reasons = []
        if stun_to:
            reasons.append(f"{len(stun_to)} STUN timeout cho thấy UDP bị chặn")
        if hard_nat:
            reasons.append("có participant sau NAT đối xứng/firewall nên srflx không hole-punch được")
        if no_relay:
            reasons.append(f"{len(no_relay)} participant không có relay candidate (TURN chưa cấu hình/không cấp phát)")
        return [self._inf(
            hypothesis="ICE thất bại do không có đường TURN relay trong khi P2P không khả thi",
            reasoning="; ".join(reasons) + ". Khi mọi cặp host/srflx fail, chỉ TURN mới cứu được -> thiếu TURN là nguyên nhân gốc.",
            derived_from=_ids(cited),
            confidence=0.9 if (stun_to or hard_nat) and no_relay else 0.6,
            recommendation="Cấu hình TURN (UDP 3478 + TCP/TLS 443) trong iceServers; kiểm tra credential TURN.",
        )]

    def _turn_fallback(self, b: FactBundle) -> list[Inference]:
        fb = b.by_tag("turn_fallback")
        if not fb:
            return []
        nat_facts = [f for f in b.by_tag("ice_gathering_complete")
                     if "nat:SYMMETRIC" in f.tags or "nat:UDP_BLOCKED" in f.tags]
        # Group call: TURN_FALLBACK gắn participant cụ thể -> chỉ xét RTT của người đó.
        # P2P: fallback áp cho cả cặp -> xét mọi participant.
        relayed = {p for f in fb for p in {s.participant_id for s in b.samples} if p in f.tags}
        relayed = relayed or {s.participant_id for s in b.samples}
        rtt_win = [w for w in b.windows if w.metric == "rtt_ms" and w.participant in relayed]
        return [self._inf(
            hypothesis="Media đi qua TURN là hành vi đúng thiết kế (NAT đối xứng/firewall), không phải lỗi",
            reasoning=(f"Log ghi TURN_FALLBACK ({len(fb)} lần) và participant liên quan có NAT "
                       f"{'SYMMETRIC/UDP_BLOCKED' if nat_facts else 'không rõ'}; "
                       + ("có thêm RTT vượt ngưỡng -> relay có thể đặt xa người dùng."
                          if rtt_win else "RTT không vượt ngưỡng -> chi phí trễ của relay chấp nhận được.")),
            derived_from=_ids(fb + nat_facts) + [w.fact_id for w in rtt_win],
            confidence=0.85 if nat_facts else 0.5,
            recommendation="Theo dõi tỉ lệ TURN usage; đặt TURN gần người dùng (geo) để giảm RTT.",
        )]

    def _loss_pattern(self, b: FactBundle) -> list[Inference]:
        out: list[Inference] = []
        for lw in [w for w in b.windows if w.metric == "packet_loss_pct"]:
            co = [w for w in b.windows if w.participant == lw.participant
                  and w.metric in ("jitter_ms", "rtt_ms") and w.overlaps(lw)]
            if co:
                out.append(self._inf(
                    hypothesis=f"Nghẽn mạng (congestion/bufferbloat) trên đường của {lw.participant} "
                               f"t={lw.start_s}-{lw.end_s}s",
                    reasoning=("Loss tăng ĐỒNG THỜI với " + ", ".join(sorted({w.metric for w in co}))
                               + " trong cùng khoảng thời gian: hàng đợi router đầy -> gói chờ lâu (jitter/RTT↑) rồi bị drop (loss↑)."),
                    derived_from=[lw.fact_id] + [w.fact_id for w in co],
                    confidence=0.8,
                    recommendation="Kiểm tra băng thông uplink; bật/kiểm tra congestion control (GCC) giảm bitrate; QoS/DSCP.",
                ))
            else:
                out.append(self._inf(
                    hypothesis=f"Mất gói ngẫu nhiên tầng vô tuyến/vật lý (Wi-Fi/4G yếu) ở {lw.participant}, không phải nghẽn",
                    reasoning="Loss vượt ngưỡng nhưng jitter và RTT KHÔNG vượt ngưỡng trong cùng khoảng -> không có dấu hiệu hàng đợi đầy.",
                    derived_from=[lw.fact_id] + _ids(b.by_tag("summary", lw.participant)),
                    confidence=0.65,
                    recommendation="Khuyên người dùng đổi mạng/lại gần AP; bật FEC (Opus in-band FEC, RED/ULPFEC).",
                ))
        return out

    def _latency_only(self, b: FactBundle) -> list[Inference]:
        out = []
        for rw in [w for w in b.windows if w.metric == "rtt_ms"]:
            if any(w.participant == rw.participant and w.metric == "packet_loss_pct" for w in b.windows):
                continue
            out.append(self._inf(
                hypothesis=f"Trễ cao ở {rw.participant} do khoảng cách/đường đi (relay hoặc định tuyến xa), không mất gói",
                reasoning="RTT vượt ngưỡng nhưng không có đoạn loss nào vượt ngưỡng cho participant này.",
                derived_from=[rw.fact_id],
                confidence=0.6,
                recommendation="Kiểm tra vị trí TURN/SFU so với người dùng; traceroute.",
            ))
        return out

    def _qoe_impact(self, b: FactBundle) -> list[Inference]:
        out = []
        for pid in sorted({w.participant for w in b.windows}):
            mos = [w for w in b.windows if w.participant == pid and w.metric in ("mos", "concealment_pct")]
            if not mos:
                continue
            causes = [w for w in b.windows if w.participant == pid and w.metric not in ("mos", "concealment_pct")]
            out.append(self._inf(
                hypothesis=f"Người dùng nghe/nhìn thấy suy giảm chất lượng rõ rệt từ luồng của {pid}",
                reasoning=("MOS/concealment vượt ngưỡng (QoE) và trùng với các vi phạm QoS: "
                           + (", ".join(sorted({w.metric for w in causes})) or "không có") + "."),
                derived_from=[w.fact_id for w in mos + causes],
                confidence=0.9 if causes else 0.6,
                recommendation="Ưu tiên audio (giảm video bitrate/resolution) khi MOS < 3.6.",
            ))
        return out

    def _sfu_isolated(self, b: FactBundle) -> list[Inference]:
        if not b.by_tag("path:SFU"):
            return []
        all_p = {s.participant_id for s in b.samples}
        bad = {w.participant for w in b.windows if w.severity == Severity.CRITICAL}
        if not bad or bad == all_p:
            return []
        healthy = sorted(all_p - bad)
        healthy_facts = [f for p in healthy for f in b.by_tag("summary", p)]
        return [self._inf(
            hypothesis=f"Sự cố cục bộ ở last-mile của {sorted(bad)}, KHÔNG phải SFU",
            reasoning=f"Cùng đi qua 1 SFU nhưng {healthy} không có vi phạm critical -> SFU vẫn khỏe; lỗi nằm ở mạng riêng của {sorted(bad)}.",
            derived_from=[w.fact_id for w in b.windows if w.participant in bad] + _ids(healthy_facts) + _ids(b.by_tag("path:SFU")),
            confidence=0.75,
            recommendation="Bật simulcast/SVC để SFU gửi layer thấp cho người mạng yếu thay vì ảnh hưởng cả phòng.",
        )]

    def _healthy(self, b: FactBundle) -> list[Inference]:
        if b.windows or b.by_code("ICE_FAILED", "CALL_FAILED"):
            return []
        summ = b.by_tag("summary")
        return [self._inf(
            hypothesis="Cuộc gọi khỏe, không phát hiện suy giảm QoS/QoE",
            reasoning="Không có đoạn metric nào vượt ngưỡng warning và không có log lỗi; các chỉ số tổng hợp nằm trong ngưỡng.",
            derived_from=_ids(summ + b.by_tag("media_established")),
            confidence=0.9,
        )]


def _ids(facts: list[Fact]) -> list[str]:
    seen: dict[str, None] = {}
    for f in facts:
        seen.setdefault(f.id, None)
    return list(seen)


# ====================================================================== facade
class DiagnosisService:
    def __init__(self, store: TelemetryStore) -> None:
        self.store = store

    def diagnose(self, call_id: str, scenario: str) -> DiagnosisReport:
        log.info("Truy vấn telemetry của %s từ store", call_id)
        events = self.store.search(EVENTS_INDEX, call_id)
        samples = [QoSSample.model_validate(d) for d in self.store.search(QOS_INDEX, call_id)]
        state = self.store.get_call_state(call_id)
        log.info("Redis call state: %s", state)

        bundle = FactExtractor().extract(events, samples)
        log.info("INFERENCE: chạy %d rule trên FACT", len(InferenceEngine().rules))
        inferences = InferenceEngine().infer(bundle)

        failed = bool(bundle.by_code("ICE_FAILED", "CALL_FAILED"))
        sev = (Severity.CRITICAL if failed or any(w.severity == Severity.CRITICAL for w in bundle.windows)
               else Severity.WARNING if bundle.windows else Severity.OK)
        path = state.get("media_path")
        return DiagnosisReport(
            call_id=call_id, scenario=scenario, verdict=sev,
            media_path=MediaPath(path) if path else None,
            summary={"final_state": state.get("state"), "events": len(events), "qos_samples": len(samples),
                     "generated_at": datetime.now().isoformat(timespec="seconds")},
            facts=bundle.facts, inferences=inferences,
        )
