"""Ordered registry of the seven deterministic M1 scenarios."""

from collections.abc import Callable
from dataclasses import dataclass

from calldiag.models import CallTelemetry
from calldiag.scenarios import (
    data,
    s0_healthy, s1_turn_overload, s2_network_p2p, s3_ice_failure,
    s4_relay_healthy, s5_signaling_timeout, s6_missing_turn_metrics,
)
from calldiag.scenarios.expected import EXPECTED_OUTCOMES, ExpectedOutcome


@dataclass(frozen=True)
class ScenarioDef:
    id: str
    title: str
    description: str
    seed: int
    build: Callable[[], CallTelemetry]
    expected: ExpectedOutcome


REGISTRY: dict[str, ScenarioDef] = {
    sid: ScenarioDef(sid, data.SCENARIO_TITLES[sid], description, data.SCENARIO_SEEDS[sid], build, EXPECTED_OUTCOMES[sid])
    for sid, build, description in (
        ("S0", s0_healthy.build, "Cuộc gọi P2P hoạt động bình thường, không có khoảng suy giảm QoS."),
        ("S1", s1_turn_overload.build, "Cuộc gọi qua relay có TURN CPU tăng cao trước khi QoS suy giảm."),
        ("S2", s2_network_p2p.build, "Mạng P2P suy giảm; đồng thời TURN server quá tải do call khác nhưng không nằm trên media path."),
        ("S3", s3_ice_failure.build, "Các candidate pair đều timeout; ICE thất bại trước khi thiết lập media."),
        ("S4", s4_relay_healthy.build, "Cuộc gọi qua TURN relay có chất lượng ổn định; dùng relay không đồng nghĩa với lỗi."),
        ("S5", s5_signaling_timeout.build, "Không nhận được ANSWER trong thời gian chờ; cuộc gọi kết thúc trước ICE và media."),
        ("S6", s6_missing_turn_metrics.build, "Cuộc gọi relay có QoS suy giảm nhưng collector không gửi metric TURN CPU."),
    )
}


def get_scenario(sid: str) -> ScenarioDef:
    try:
        return REGISTRY[sid]
    except KeyError:
        raise KeyError(f"Unknown scenario {sid!r}. Valid IDs: {', '.join(REGISTRY)}") from None


def build_all() -> dict[str, CallTelemetry]:
    return {sid: scenario.build() for sid, scenario in REGISTRY.items()}
