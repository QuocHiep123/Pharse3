"""Các kịch bản test luồng cuộc gọi end-to-end."""

from __future__ import annotations

from pydantic import BaseModel, Field

from callops.models import Impairment, NatType, NetworkCondition, Participant


class Scenario(BaseModel):
    name: str
    description: str
    participants: list[Participant] = Field(min_length=2)
    turn_available: bool = True
    duration_s: int = 30
    impairments: list[Impairment] = Field(default_factory=list)
    expected: str = ""

    @property
    def is_group(self) -> bool:
        return len(self.participants) > 2


GOOD = NetworkCondition(base_rtt_ms=60, jitter_ms=4, loss_pct=0.2)

SCENARIOS: dict[str, Scenario] = {
    s.name: s
    for s in [
        Scenario(
            name="p2p_good",
            description="2 người, NAT cone thông thường, mạng tốt -> P2P qua STUN",
            participants=[
                Participant(id="alice", nat=NatType.FULL_CONE, lan="home-a", network=GOOD),
                Participant(id="bob", nat=NatType.PORT_RESTRICTED, lan="home-b", network=GOOD),
            ],
            expected="P2P_STUN, verdict OK",
        ),
        Scenario(
            name="same_lan",
            description="2 người cùng mạng LAN văn phòng -> P2P host candidate",
            participants=[
                Participant(id="alice", nat=NatType.PORT_RESTRICTED, lan="office", network=GOOD),
                Participant(id="bob", nat=NatType.PORT_RESTRICTED, lan="office", network=GOOD),
            ],
            expected="P2P_HOST, verdict OK",
        ),
        Scenario(
            name="symmetric_nat_turn",
            description="Caller sau NAT đối xứng (4G/CGNAT) -> srflx thất bại, fallback TURN",
            participants=[
                Participant(id="alice", nat=NatType.SYMMETRIC, lan="mobile-4g",
                            network=NetworkCondition(base_rtt_ms=90, jitter_ms=8, loss_pct=0.5)),
                Participant(id="bob", nat=NatType.PORT_RESTRICTED, lan="home-b", network=GOOD),
            ],
            expected="TURN_RELAY, verdict OK (RTT cao hơn do relay)",
        ),
        Scenario(
            name="ice_failed_no_turn",
            description="Firewall công ty chặn UDP + TURN không cấu hình -> ICE failed",
            participants=[
                Participant(id="alice", nat=NatType.UDP_BLOCKED, lan="corp", network=GOOD),
                Participant(id="bob", nat=NatType.SYMMETRIC, lan="mobile-4g", network=GOOD),
            ],
            turn_available=False,
            expected="FAILED (ICE_FAILED), verdict CRITICAL",
        ),
        Scenario(
            name="congestion",
            description="P2P, từ giây 10-20 uplink của bob bị nghẽn (loss + jitter + RTT tăng cùng lúc)",
            participants=[
                Participant(id="alice", nat=NatType.FULL_CONE, lan="home-a", network=GOOD),
                Participant(id="bob", nat=NatType.FULL_CONE, lan="home-b", network=GOOD),
            ],
            impairments=[
                Impairment(participant_id="bob", start_s=10, end_s=20, extra_rtt_ms=250,
                           extra_jitter_ms=55, extra_loss_pct=7, note="bufferbloat / uplink congestion"),
            ],
            expected="P2P_STUN, verdict CRITICAL, inference: nghẽn mạng uplink bob",
        ),
        Scenario(
            name="wifi_loss",
            description="Mất gói ngẫu nhiên ~3% (sóng Wi-Fi yếu) nhưng jitter/RTT bình thường",
            participants=[
                Participant(id="alice", nat=NatType.FULL_CONE, lan="cafe-wifi",
                            network=NetworkCondition(base_rtt_ms=70, jitter_ms=6, loss_pct=3.0)),
                Participant(id="bob", nat=NatType.FULL_CONE, lan="home-b", network=GOOD),
            ],
            expected="verdict WARNING, inference: mất gói tầng vô tuyến, không phải nghẽn",
        ),
        Scenario(
            name="group_sfu",
            description="Gọi nhóm 4 người qua SFU, 1 người (dave) có last-mile kém",
            participants=[
                Participant(id="alice", nat=NatType.FULL_CONE, lan="home-a", network=GOOD),
                Participant(id="bob", nat=NatType.SYMMETRIC, lan="mobile-4g", network=GOOD),
                Participant(id="carol", nat=NatType.UDP_BLOCKED, lan="corp", network=GOOD),
                Participant(id="dave", nat=NatType.PORT_RESTRICTED, lan="rural",
                            network=NetworkCondition(base_rtt_ms=380, jitter_ms=45, loss_pct=6)),
            ],
            expected="SFU, carol vào SFU qua TURN/TLS, verdict CRITICAL chỉ do dave",
        ),
    ]
}
