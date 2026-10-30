"""Data model (Pydantic v2) cho toàn bộ domain: cuộc gọi, ICE, QoS, FACT/INFERENCE."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------- call domain
class CallState(str, Enum):
    IDLE = "IDLE"
    SETUP = "SETUP"                      # signaling: INVITE / join room
    OFFER_SENT = "OFFER_SENT"            # SDP offer đã gửi
    ANSWER_RECEIVED = "ANSWER_RECEIVED"  # SDP answer đã nhận
    ICE_CHECKING = "ICE_CHECKING"        # trao đổi candidate + connectivity check
    CONNECTED = "CONNECTED"              # media established (DTLS-SRTP chạy)
    TERMINATED = "TERMINATED"            # kết thúc bình thường (BYE)
    FAILED = "FAILED"                    # kết thúc lỗi


class NatType(str, Enum):
    OPEN = "OPEN"                        # IP public, không NAT
    FULL_CONE = "FULL_CONE"
    PORT_RESTRICTED = "PORT_RESTRICTED"
    SYMMETRIC = "SYMMETRIC"              # mapping đổi theo đích -> srflx vô dụng với peer
    UDP_BLOCKED = "UDP_BLOCKED"          # firewall chặn UDP -> chỉ đi được TURN/TCP-TLS 443


class CandidateType(str, Enum):
    HOST = "host"    # IP local của máy
    SRFLX = "srflx"  # server-reflexive: IP public học từ STUN
    RELAY = "relay"  # địa chỉ cấp phát trên TURN server


class MediaPath(str, Enum):
    P2P_HOST = "P2P_HOST"      # cùng LAN
    P2P_STUN = "P2P_STUN"      # xuyên NAT nhờ STUN (srflx <-> srflx)
    TURN_RELAY = "TURN_RELAY"  # media đi vòng qua TURN
    SFU = "SFU"                # gọi nhóm: mỗi người gửi 1 luồng lên SFU, SFU forward


class Severity(str, Enum):
    OK = "OK"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class NetworkCondition(BaseModel):
    """Đặc tính mạng 'thật' của 1 participant (dùng để sinh metric)."""

    base_rtt_ms: float = 60.0
    jitter_ms: float = 5.0
    loss_pct: float = 0.2


class Impairment(BaseModel):
    """Sự cố mạng chèn vào trong khoảng thời gian [start_s, end_s)."""

    participant_id: str
    start_s: int
    end_s: int
    extra_rtt_ms: float = 0.0
    extra_jitter_ms: float = 0.0
    extra_loss_pct: float = 0.0
    note: str = ""


class Participant(BaseModel):
    id: str
    nat: NatType = NatType.FULL_CONE
    lan: str = "lan-a"
    network: NetworkCondition = Field(default_factory=NetworkCondition)


class IceCandidate(BaseModel):
    participant_id: str
    type: CandidateType
    ip: str
    port: int
    protocol: str = "udp"
    priority: int

    def sdp_line(self) -> str:
        return (
            f"a=candidate:1 1 {self.protocol} {self.priority} {self.ip} {self.port} typ {self.type.value}"
        )


# ---------------------------------------------------------------- telemetry
class CallEvent(BaseModel):
    """1 dòng log signaling/media của cuộc gọi (sẽ được index vào OpenSearch)."""

    ts: datetime
    call_id: str
    level: str = "INFO"
    event: str
    state: CallState
    error_code: str | None = None
    message: str
    detail: dict[str, Any] = Field(default_factory=dict)


class QoSSample(BaseModel):
    """1 mẫu metric/giây của 1 participant (giống getStats() của WebRTC)."""

    ts: datetime
    call_id: str
    participant_id: str
    t_s: int
    rtt_ms: float
    jitter_ms: float
    packet_loss_pct: float
    mos: float
    video_freeze_count: int
    concealment_pct: float


# ---------------------------------------------------------------- AIOps
class Fact(BaseModel):
    """FACT: dữ kiện lấy trực tiếp từ log/metric. Bắt buộc có timestamp + evidence gốc."""

    id: str
    ts: datetime
    source: str  # "log" | "metric"
    statement: str
    evidence: str = Field(min_length=1)
    error_code: str | None = None
    tags: list[str] = Field(default_factory=list)


class Inference(BaseModel):
    """INFERENCE: giả thuyết suy ra từ FACT. Bắt buộc trỏ về >= 1 FACT + có lập luận."""

    id: str
    hypothesis: str
    reasoning: str = Field(min_length=1)
    derived_from: list[str] = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    recommendation: str = ""


class DiagnosisReport(BaseModel):
    call_id: str
    scenario: str
    verdict: Severity
    media_path: MediaPath | None
    summary: dict[str, Any] = Field(default_factory=dict)
    facts: list[Fact]
    inferences: list[Inference]

    @model_validator(mode="after")
    def _inferences_must_cite_existing_facts(self) -> "DiagnosisReport":
        fact_ids = {f.id for f in self.facts}
        for inf in self.inferences:
            missing = [fid for fid in inf.derived_from if fid not in fact_ids]
            if missing:
                raise ValueError(f"{inf.id} trích dẫn FACT không tồn tại: {missing}")
        return self
