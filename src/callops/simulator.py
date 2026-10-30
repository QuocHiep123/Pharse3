"""Mô phỏng luồng cuộc gọi WebRTC:

  Call Setup -> SDP Offer/Answer -> ICE gathering + exchange + connectivity checks
             -> Media Established (QoS sampling) -> Call Termination

Mọi bước đều phát ra CallEvent: log ra console/JSONL, index vào OpenSearch,
cập nhật trạng thái cuộc gọi trong Redis. AIOps sau đó chỉ đọc lại từ store.
"""

from __future__ import annotations

import logging
import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from callops.models import (
    CallEvent,
    CallState,
    CandidateType,
    IceCandidate,
    MediaPath,
    NatType,
    Participant,
    QoSSample,
    Severity,
)
from callops.qos import THRESHOLDS, QoSGenerator
from callops.scenarios import Scenario
from callops.storage import EVENTS_INDEX, QOS_INDEX, TelemetryStore

log = logging.getLogger("callops.call")
ice_log = logging.getLogger("callops.ice")
media_log = logging.getLogger("callops.media")

SFU_ADDR = ("203.0.113.10", 10000)
TURN_ADDR = "198.51.100.20"
TYPE_PREF = {CandidateType.HOST: 126, CandidateType.SRFLX: 100, CandidateType.RELAY: 0}


@dataclass
class SimClock:
    """Đồng hồ giả lập -> timestamp tất định, dễ đối chiếu FACT."""

    now: datetime = field(default_factory=lambda: datetime(2026, 10, 30, 9, 0, 0, tzinfo=timezone.utc))

    def advance(self, ms: float) -> datetime:
        self.now += timedelta(milliseconds=ms)
        return self.now


@dataclass
class CallResult:
    call_id: str
    final_state: CallState
    media_path: MediaPath | None
    connected: list[str]


def _priority(ctype: CandidateType, local_pref: int = 65535) -> int:
    # RFC 8445: priority = 2^24*type_pref + 2^8*local_pref + (256 - component_id)
    return (2**24) * TYPE_PREF[ctype] + (2**8) * local_pref + 255


class CallSimulator:
    def __init__(self, scenario: Scenario, store: TelemetryStore, seed: int = 42) -> None:
        self.sc = scenario
        self.store = store
        self.rng = random.Random(seed)
        self.clock = SimClock()
        self.call_id = f"call-{scenario.name}-{uuid.UUID(int=self.rng.getrandbits(128)).hex[:8]}"
        self.state = CallState.IDLE
        self.qos = QoSGenerator(self.rng)

    # ------------------------------------------------------------ helpers
    def _emit(self, event: str, message: str, *, state: CallState | None = None, level: str = "INFO",
              error_code: str | None = None, logger: logging.Logger = log, **detail: Any) -> CallEvent:
        if state is not None and state != self.state:
            logger.info("STATE %s -> %s", self.state.value, state.value, extra={"call_id": self.call_id})
            self.state = state
            self.store.set_call_state(self.call_id, {"state": state.value, "updated_at": self.clock.now.isoformat()})
        ev = CallEvent(ts=self.clock.now, call_id=self.call_id, level=level, event=event, state=self.state,
                       error_code=error_code, message=message, detail=detail)
        self.store.index(EVENTS_INDEX, ev.model_dump(mode="json"))
        extra = {"sim_ts": ev.ts.strftime("%H:%M:%S.%f")[:-3], "event": event}
        if error_code:
            extra["error_code"] = error_code
        extra.update({k: v for k, v in detail.items() if not isinstance(v, (list, dict))})
        logger.log(logging.getLevelName(level), message, extra=extra)
        return ev

    @staticmethod
    def _step(n: int, title: str) -> None:
        log.info("━" * 18 + f" [STEP {n}] {title} " + "━" * 18)

    # ------------------------------------------------------------ flow
    def run(self) -> CallResult:
        sc = self.sc
        log.info("▶ Bắt đầu kịch bản '%s': %s", sc.name, sc.description)
        log.info("  call_id=%s | participants=%s | TURN=%s | kỳ vọng: %s", self.call_id,
                 [f"{p.id}({p.nat.value})" for p in sc.participants], sc.turn_available, sc.expected)
        self.store.set_call_state(self.call_id, {
            "scenario": sc.name, "participants": ",".join(p.id for p in sc.participants),
        })

        self._step(1, "CALL SETUP (signaling qua WebSocket)")
        self._setup()
        self._step(2, "SDP OFFER / ANSWER")
        self._offer_answer()
        self._step(3, "ICE: gathering candidates (host / STUN srflx / TURN relay)")
        candidates = {p.id: self._gather(p) for p in sc.participants}
        self._step(4, "ICE: trao đổi candidate + connectivity checks")
        path, connected = (self._ice_group(candidates) if sc.is_group else self._ice_p2p(candidates))

        if path is None:
            self._step(5, "CALL TERMINATION (lỗi)")
            self._emit("CALL_FAILED", "Cuộc gọi thất bại: không thiết lập được media", state=CallState.FAILED,
                       level="ERROR", error_code="ICE_FAILED")
            self.store.flush()
            return CallResult(self.call_id, self.state, None, [])

        self._step(5, f"MEDIA ESTABLISHED qua {path.value} - đo QoS {sc.duration_s}s")
        self._media(path, connected)
        self._step(6, "CALL TERMINATION (BYE)")
        self.clock.advance(200)
        self._emit("BYE", f"{connected[0]} gửi BYE, giải phóng PeerConnection/TURN allocation",
                   state=CallState.TERMINATED, duration_s=sc.duration_s)
        self.store.flush()
        return CallResult(self.call_id, self.state, path, connected)

    def _setup(self) -> None:
        caller, *callees = self.sc.participants
        self.clock.advance(30)
        kind = "JOIN_ROOM" if self.sc.is_group else "INVITE"
        self._emit(kind, f"{caller.id} -> signaling server: {kind} tới {[c.id for c in callees]}",
                   state=CallState.SETUP, caller=caller.id)
        for c in callees:
            self.clock.advance(self.rng.uniform(150, 400))
            self._emit("RINGING_ACCEPTED", f"{c.id} chấp nhận cuộc gọi", callee=c.id)

    def _offer_answer(self) -> None:
        caller = self.sc.participants[0]
        sdp = [
            "v=0", "o=- 4611731400430051336 2 IN IP4 127.0.0.1", "s=-", "t=0 0",
            "a=group:BUNDLE 0 1", "m=audio 9 UDP/TLS/RTP/SAVPF 111", "a=rtpmap:111 opus/48000/2",
            "m=video 9 UDP/TLS/RTP/SAVPF 96", "a=rtpmap:96 VP8/90000",
            f"a=ice-ufrag:{self.rng.getrandbits(32):08x}", "a=fingerprint:sha-256 AB:CD:...:EF",
        ]
        self.clock.advance(20)
        log.debug("SDP offer:\n    " + "\n    ".join(sdp))
        self._emit("SDP_OFFER", f"{caller.id} createOffer() + setLocalDescription(); gửi offer (opus + VP8, BUNDLE)",
                   state=CallState.OFFER_SENT, sdp_lines=len(sdp))
        self.clock.advance(self.rng.uniform(80, 160))
        self._emit("SDP_ANSWER", "Nhận answer -> setRemoteDescription(); codec chốt: audio=opus video=VP8",
                   state=CallState.ANSWER_RECEIVED, audio_codec="opus", video_codec="VP8")

    def _gather(self, p: Participant) -> list[IceCandidate]:
        cands: list[IceCandidate] = []
        host_ip = f"192.168.{self.rng.randint(0, 9)}.{self.rng.randint(2, 250)}"
        cands.append(IceCandidate(participant_id=p.id, type=CandidateType.HOST, ip=host_ip,
                                  port=self.rng.randint(50000, 60000), priority=_priority(CandidateType.HOST)))
        self.clock.advance(5)

        if p.nat == NatType.UDP_BLOCKED:
            self.clock.advance(3000)
            self._emit("STUN_TIMEOUT", f"[{p.id}] STUN Binding Request qua UDP timeout 3s (firewall chặn UDP)",
                       level="WARNING", error_code="STUN_TIMEOUT", logger=ice_log, participant=p.id)
        else:
            pub = f"{self.rng.choice([14, 27, 113, 171])}.{self.rng.randint(1, 250)}.{self.rng.randint(1, 250)}.{self.rng.randint(1, 250)}"
            self.clock.advance(self.rng.uniform(20, 60))
            cands.append(IceCandidate(participant_id=p.id, type=CandidateType.SRFLX, ip=pub,
                                      port=self.rng.randint(1024, 65000), priority=_priority(CandidateType.SRFLX)))
            ice_log.debug("[%s] STUN Binding Response: XOR-MAPPED-ADDRESS=%s", p.id, pub)

        if self.sc.turn_available:
            proto = "tcp" if p.nat == NatType.UDP_BLOCKED else "udp"
            port = 443 if proto == "tcp" else 3478
            self.clock.advance(self.rng.uniform(40, 90))
            cands.append(IceCandidate(participant_id=p.id, type=CandidateType.RELAY, ip=TURN_ADDR,
                                      port=self.rng.randint(49152, 65535), protocol=proto,
                                      priority=_priority(CandidateType.RELAY)))
            ice_log.debug("[%s] TURN Allocate thành công qua %s/%d (cấp relay port)", p.id, proto.upper(), port)
        else:
            ice_log.debug("[%s] Không có TURN server trong iceServers -> không có relay candidate", p.id)

        for c in cands:
            ice_log.debug("[%s] %s", p.id, c.sdp_line())
        self._emit("ICE_GATHERING_COMPLETE", f"[{p.id}] gathered {len(cands)} candidate: "
                   f"{[c.type.value for c in cands]}", logger=ice_log, participant=p.id, nat=p.nat.value,
                   candidate_types=",".join(c.type.value for c in cands))
        return cands

    def _check(self, a: Participant, ca: IceCandidate, b: Participant | None, cb: IceCandidate | None) -> tuple[bool, str]:
        """Luật connectivity check (đơn giản hóa hành vi NAT)."""
        if b is None:  # tới SFU (IP public)
            if ca.type == CandidateType.RELAY:
                return True, "TURN relay -> SFU OK"
            if a.nat == NatType.UDP_BLOCKED:
                return False, "UDP bị chặn"
            return True, "SFU có IP public, NAT nào cũng ra được"
        assert cb is not None
        if CandidateType.RELAY in (ca.type, cb.type):
            return True, "media đi qua TURN relay"
        if ca.type == cb.type == CandidateType.HOST:
            return (a.lan == b.lan, "cùng LAN" if a.lan == b.lan else "khác LAN, IP private không route được")
        if ca.type == cb.type == CandidateType.SRFLX:
            hard = {NatType.SYMMETRIC, NatType.PORT_RESTRICTED}
            if NatType.SYMMETRIC in (a.nat, b.nat) and a.nat in hard and b.nat in hard:
                return False, "NAT đối xứng: mapping port đổi theo đích, hole-punching thất bại"
            return True, "hole-punching qua NAT thành công"
        return False, "cặp candidate không tương thích"

    def _ice_p2p(self, cands: dict[str, list[IceCandidate]]) -> tuple[MediaPath | None, list[str]]:
        a, b = self.sc.participants
        self._emit("ICE_CANDIDATES_EXCHANGED", "Trao đổi candidate qua signaling (trickle ICE)",
                   state=CallState.ICE_CHECKING, logger=ice_log,
                   local=len(cands[a.id]), remote=len(cands[b.id]))
        pairs = sorted(
            ((ca, cb) for ca in cands[a.id] for cb in cands[b.id]),
            key=lambda pr: min(pr[0].priority, pr[1].priority), reverse=True,
        )
        for ca, cb in pairs:
            self.clock.advance(self.rng.uniform(30, 120))
            ok, why = self._check(a, ca, b, cb)
            ice_log.debug("check %s:%s(%s) <-> %s:%s(%s): %s - %s", ca.ip, ca.port, ca.type.value,
                          cb.ip, cb.port, cb.type.value, "SUCCEEDED" if ok else "FAILED", why)
            if ok:
                path = (MediaPath.TURN_RELAY if CandidateType.RELAY in (ca.type, cb.type)
                        else MediaPath.P2P_HOST if ca.type == CandidateType.HOST else MediaPath.P2P_STUN)
                if path == MediaPath.TURN_RELAY:
                    self._emit("TURN_FALLBACK", "Không có cặp P2P nào thành công -> fallback TURN relay",
                               level="WARNING", logger=ice_log, reason="p2p_pairs_failed",
                               nats=f"{a.nat.value}/{b.nat.value}")
                self._emit("ICE_SELECTED_PAIR", f"Nominated pair {ca.type.value}<->{cb.type.value}: {why}",
                           logger=ice_log, media_path=path.value, local_type=ca.type.value,
                           remote_type=cb.type.value)
                return path, [a.id, b.id]
        self._emit("ICE_FAILED", f"Tất cả {len(pairs)} cặp candidate đều FAILED; không có relay candidate",
                   level="ERROR", error_code="ICE_FAILED", logger=ice_log, pairs_checked=len(pairs),
                   turn_configured=self.sc.turn_available, nats=f"{a.nat.value}/{b.nat.value}")
        return None, []

    def _ice_group(self, cands: dict[str, list[IceCandidate]]) -> tuple[MediaPath | None, list[str]]:
        self._emit("ICE_CANDIDATES_EXCHANGED", f"Mỗi participant trao đổi ICE với SFU {SFU_ADDR[0]}",
                   state=CallState.ICE_CHECKING, logger=ice_log)
        connected: list[str] = []
        for p in self.sc.participants:
            for c in sorted(cands[p.id], key=lambda c: c.priority, reverse=True):
                self.clock.advance(self.rng.uniform(30, 90))
                ok, why = self._check(p, c, None, None)
                ice_log.debug("[%s] check %s(%s) -> SFU %s:%d: %s - %s", p.id, c.ip, c.type.value,
                              *SFU_ADDR, "SUCCEEDED" if ok else "FAILED", why)
                if ok:
                    if c.type == CandidateType.RELAY:
                        self._emit("TURN_FALLBACK", f"[{p.id}] vào SFU qua TURN/{c.protocol.upper()} 443",
                                   level="WARNING", logger=ice_log, participant=p.id, nats=p.nat.value,
                                   reason="udp_blocked")
                    self._emit("SFU_CONNECTED", f"[{p.id}] kết nối SFU bằng {c.type.value}", logger=ice_log,
                               participant=p.id, candidate_type=c.type.value)
                    connected.append(p.id)
                    break
            else:
                self._emit("ICE_FAILED", f"[{p.id}] không kết nối được SFU", level="ERROR",
                           error_code="ICE_FAILED", logger=ice_log, participant=p.id)
        if len(connected) < 2:
            return None, connected
        self._emit("ICE_SELECTED_PAIR", f"{len(connected)}/{len(self.sc.participants)} participant đã vào SFU",
                   logger=ice_log, media_path=MediaPath.SFU.value)
        return MediaPath.SFU, connected

    def _media(self, path: MediaPath, connected: list[str]) -> None:
        self.clock.advance(150)
        self._emit("MEDIA_ESTABLISHED", "DTLS handshake xong, SRTP audio/video bắt đầu chảy",
                   state=CallState.CONNECTED, logger=media_log, media_path=path.value)
        self.store.set_call_state(self.call_id, {"media_path": path.value})
        start = self.clock.now
        parts = {p.id: p for p in self.sc.participants if p.id in connected}
        level_now: dict[tuple[str, str], Severity] = {}

        for t in range(self.sc.duration_s):
            for pid, p in parts.items():
                s = self.qos.sample(call_id=self.call_id, participant_id=pid, t_s=t, start=start,
                                    network=p.network, path=path, impairments=self.sc.impairments)
                self.store.index(QOS_INDEX, s.model_dump(mode="json"))
                media_log.debug("t=%02ds %-6s rtt=%6.1fms jitter=%5.1fms loss=%5.2f%% MOS=%.2f freeze=%d",
                                t, pid, s.rtt_ms, s.jitter_ms, s.packet_loss_pct, s.mos, s.video_freeze_count)
                self._alerts(s, level_now)
            self.clock.now = start + timedelta(seconds=t + 1)

    def _alerts(self, s: QoSSample, level_now: dict[tuple[str, str], Severity]) -> None:
        """Phát QOS_ALERT khi metric đổi mức (OK->WARNING->CRITICAL) và QOS_RECOVERED khi về OK."""
        for metric, th in THRESHOLDS.items():
            value = getattr(s, metric)
            sev = th.classify(value)
            key = (s.participant_id, metric)
            prev = level_now.get(key, Severity.OK)
            if sev == prev:
                continue
            level_now[key] = sev
            saved, self.clock.now = self.clock.now, s.ts
            if sev == Severity.OK:
                self._emit("QOS_RECOVERED", f"[{s.participant_id}] {metric} về bình thường ({value})",
                           logger=media_log, participant=s.participant_id, metric=metric, value=value)
            else:
                limit = th.critical if sev == Severity.CRITICAL else th.warning
                self._emit("QOS_ALERT", f"[{s.participant_id}] {metric}={value} vượt ngưỡng {sev.value} ({limit})",
                           level="WARNING", error_code=f"QOS_{metric.upper()}_{sev.value}", logger=media_log,
                           participant=s.participant_id, metric=metric, value=value, severity=sev.value)
            self.clock.now = saved
