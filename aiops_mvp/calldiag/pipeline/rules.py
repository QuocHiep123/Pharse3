"""FACT-only conditions and the deterministic rule catalog."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import timedelta

from calldiag import config
from calldiag.models import (
    PHASE_ORDER, AnomalyResult, ConditionResult, CondState, EvidenceBundle,
    Fact, FactKind, PathContext, Phase, PhaseSpan,
)
from calldiag.pipeline.facts import FactStore
from calldiag.utils import fmt_window


@dataclass
class Ctx:
    facts: FactStore
    phases: list[PhaseSpan]
    path: PathContext
    anomalies: AnomalyResult
    evidence: list[EvidenceBundle]

    @property
    def focus_ref(self) -> str | None:
        return self.evidence[0].focus_ref if self.evidence else None

    def focus_window_str(self) -> str:
        if self.evidence and self.evidence[0].focus_ref is not None:
            return fmt_window(self.evidence[0].focus_start, self.evidence[0].focus_end)
        return ""

    def changes(self, **filters: object) -> list[Fact]:
        return [fact for fact in self.facts.query(FactKind.METRIC_CHANGE, **filters)
                if self.focus_ref is None or self.focus_ref in fact.data.get("interval_ids", [])]


Condition = Callable[[Ctx], ConditionResult]
TextBuilder = Callable[[Ctx], str]
ChecksBuilder = Callable[[Ctx], list[str]]
RejectionBuilder = Callable[[Ctx, list[ConditionResult]], str]


def _no_checks(ctx: Ctx) -> list[str]:
    return []


@dataclass(frozen=True)
class RuleSpec:
    rule_id: str
    title: str
    specificity: int
    preconditions: tuple[Condition, ...]
    required: tuple[Condition, ...]
    conclusion: TextBuilder
    hypothesis_statement: TextBuilder
    boosters: tuple[Condition, ...] = ()
    counters: tuple[Condition, ...] = ()
    missing_penalties: tuple[Condition, ...] = ()
    alternatives: tuple[str, ...] = ()
    unknowns: tuple[str, ...] = ()
    next_checks: ChecksBuilder = _no_checks
    # Optional rule-specific wording for REJECTED; default joins the FALSE conditions.
    rejection_reason: RejectionBuilder | None = None


def _condition(
    name: str, description: str, state: CondState, facts: Sequence[Fact] = (), note: str | None = None,
) -> ConditionResult:
    return ConditionResult(name=name, description=description, state=state,
                           fact_ids=list(dict.fromkeys(f.fact_id for f in facts)), note=note)


def qos_incident(ctx: Ctx) -> ConditionResult:
    changes = ctx.changes(category="qos")
    levels = ctx.facts.query(FactKind.METRIC_LEVEL, category="qos", scope="media_phase")
    missing = [f for f in ctx.facts.query(FactKind.MISSING_DATA) if config.METRIC_META[f.metric]["category"] == "qos"]
    state = CondState.TRUE if changes else CondState.UNKNOWN if missing else CondState.FALSE if levels else CondState.UNKNOWN
    return _condition("qos_incident", "Có QoS incident được quan sát", state, changes or missing or levels)


def no_qos_anomaly(ctx: Ctx) -> ConditionResult:
    result = qos_incident(ctx)
    return result.model_copy(update={"name": "no_qos_anomaly", "description": "Không ghi nhận QoS anomaly theo rule",
                                     "state": {CondState.TRUE: CondState.FALSE, CondState.FALSE: CondState.TRUE, CondState.UNKNOWN: CondState.UNKNOWN}[result.state]})


def phase_failed(phase: Phase | str) -> Condition:
    phase = Phase(phase)

    def check(ctx: Ctx) -> ConditionResult:
        facts = ctx.facts.query(FactKind.PHASE_STATUS, phase=phase.value)
        state = CondState.UNKNOWN if not facts else CondState.TRUE if facts[0].data["status"] == "failed" else CondState.FALSE
        return _condition(f"phase_failed({phase.value})", f"Phase {phase.value} thất bại", state, facts)
    return check


def all_phases_ok(ctx: Ctx) -> ConditionResult:
    facts = ctx.facts.query(FactKind.PHASE_STATUS)
    bad = [f for f in facts if f.data["status"] not in {"ok", "degraded"}]
    complete = {f.data["phase"] for f in facts} == {p.value for p in PHASE_ORDER}
    state = CondState.FALSE if bad else CondState.TRUE if complete else CondState.UNKNOWN
    return _condition("all_phases_ok", "Cả 5 phase hoàn tất", state, bad or facts)


def media_ok(ctx: Ctx) -> ConditionResult:
    facts = ctx.facts.query(FactKind.PHASE_STATUS, phase="media")
    state = CondState.UNKNOWN if not facts else CondState.TRUE if facts[0].data["status"] in {"ok", "degraded"} else CondState.FALSE
    return _condition("media_ok", "Media được thiết lập", state, facts)


def via_turn(ctx: Ctx) -> ConditionResult:
    facts = ctx.facts.query(FactKind.SELECTED_PATH)
    state = CondState.UNKNOWN if not facts else CondState.TRUE if facts[0].data["via_turn"] else CondState.FALSE
    return _condition("via_turn", "TURN nằm trên selected path", state, facts)


def _resource_high(ctx: Ctx, metric: str) -> tuple[CondState, list[Fact]]:
    high = ctx.changes(metric=metric)
    normal = [f for f in ctx.facts.query(FactKind.METRIC_LEVEL, metric=metric, scope="interval")
              if ctx.focus_ref is None or f.data.get("interval_id") == ctx.focus_ref]
    missing = ctx.facts.query(FactKind.MISSING_DATA, metric=metric)
    if metric == "turn_cpu_pct":
        routes = ctx.facts.query(FactKind.SELECTED_PATH)
        turn = routes[0].data.get("turn_server") if routes else None
        if turn is not None:
            high = [f for f in high if f.source == turn and f.data.get("on_path") is True]
            normal = [f for f in normal if f.source == turn]
            missing = [f for f in missing if f.source == turn]
    return (CondState.TRUE, high) if high else (CondState.FALSE, normal) if normal else (CondState.UNKNOWN, missing)


def turn_cpu_high_overlap(ctx: Ctx) -> ConditionResult:
    state, facts = _resource_high(ctx, "turn_cpu_pct")
    return _condition("turn_cpu_high_overlap", "TURN CPU cao và chồng lấn incident", state, facts,
                      "thiếu turn_cpu_pct để xác minh" if state == CondState.UNKNOWN else None)


def turn_cpu_on_path_high(ctx: Ctx) -> ConditionResult:
    route, cpu = via_turn(ctx), turn_cpu_high_overlap(ctx)
    facts = [ctx.facts.get(fid) for fid in dict.fromkeys(route.fact_ids + cpu.fact_ids)]
    state = CondState.FALSE if route.state == CondState.FALSE or cpu.state == CondState.FALSE else (
        CondState.TRUE if route.state == cpu.state == CondState.TRUE else CondState.UNKNOWN
    )
    note = "TURN không nằm trên selected path" if route.state == CondState.FALSE else cpu.note
    return _condition("turn_cpu_on_path_high", "TURN CPU cao trên selected path", state, facts, note)


def turn_cpu_precedes_qos(ctx: Ctx) -> ConditionResult:
    turn, qos = _resource_high(ctx, "turn_cpu_pct")[1], ctx.changes(category="qos")
    turn = [f for f in turn if f.kind == FactKind.METRIC_CHANGE]
    if not turn or not qos:
        return _condition("turn_cpu_precedes_qos", "TURN CPU tăng trước QoS", CondState.UNKNOWN, turn + qos)
    state = CondState.TRUE if min(f.data["start_offset_sec"] for f in turn) <= min(f.data["start_offset_sec"] for f in qos) + config.PRECEDENCE_TOLERANCE_SEC else CondState.FALSE
    return _condition("turn_cpu_precedes_qos", "TURN CPU tăng trước QoS trong tolerance", state, turn + qos)


def turn_logs_on_path(ctx: Ctx) -> ConditionResult:
    routes = ctx.facts.query(FactKind.SELECTED_PATH)
    turn = routes[0].data.get("turn_server") if routes else None
    focuses = ctx.changes(category="qos")
    starts = [f.window_start for f in focuses if f.window_start is not None]
    ends = [f.window_end for f in focuses if f.window_end is not None]
    facts = [f for f in ctx.facts.query(FactKind.LOG_EVENT, component=turn, on_path=True)
             if f.data.get("same_call") is not False and f.ts is not None and starts and ends
             and min(starts) - timedelta(seconds=config.CORRELATION_PRE_SEC) <= f.ts <= max(ends) + timedelta(seconds=config.CORRELATION_POST_SEC)]
    return _condition("turn_logs_on_path", "Có log TURN trên path gần incident", CondState.TRUE if facts else CondState.FALSE, facts)


def client_cpu_high(ctx: Ctx) -> ConditionResult:
    state, facts = _resource_high(ctx, "client_cpu_pct")
    return _condition("client_cpu_high", "Client CPU cao trong incident", state, facts)


def rtt_or_loss_anomaly(ctx: Ctx) -> ConditionResult:
    facts = [f for f in ctx.changes(category="qos") if f.metric in {"rtt_ms", "packet_loss_pct"}]
    return _condition("rtt_or_loss_anomaly", "RTT hoặc packet loss có anomaly", CondState.TRUE if facts else CondState.FALSE, facts)


def multi_qos_metrics(ctx: Ctx) -> ConditionResult:
    facts = ctx.changes(category="qos")
    state = CondState.TRUE if len({f.metric for f in facts}) >= config.MULTI_QOS_MIN_METRICS else CondState.FALSE
    return _condition("multi_qos_metrics", "Nhiều metric QoS cùng suy giảm", state, facts)


def turn_metrics_missing_on_relay(ctx: Ctx) -> ConditionResult:
    route = via_turn(ctx)
    missing = ctx.facts.query(FactKind.MISSING_DATA, metric="turn_cpu_pct")
    paths = ctx.facts.query(FactKind.SELECTED_PATH)
    if paths and paths[0].data.get("turn_server") is not None:
        missing = [f for f in missing if f.source == paths[0].data["turn_server"]]
    state = CondState.TRUE if route.state == CondState.TRUE and missing else CondState.FALSE
    return _condition("turn_metrics_missing_on_relay", "Thiếu turn_cpu_pct để loại trừ TURN trên relay", state,
                      [ctx.facts.get(fid) for fid in route.fact_ids] + missing)


def all_pairs_failed(ctx: Ctx) -> ConditionResult:
    facts = ctx.facts.query(FactKind.ICE_CHECKS)
    state = CondState.UNKNOWN if not facts or facts[0].data["total"] == 0 else CondState.TRUE if facts[0].data["succeeded"] == 0 else CondState.FALSE
    return _condition("all_pairs_failed", "Mọi candidate pair được thử đều thất bại", state, facts)


def relay_pair_attempted(ctx: Ctx) -> ConditionResult:
    facts = ctx.facts.query(FactKind.ICE_CHECKS)
    state = CondState.UNKNOWN if not facts else CondState.TRUE if facts[0].data["relay_pair_failed"] else CondState.FALSE
    return _condition("relay_pair_attempted", "Relay pair đã được thử và thất bại", state, facts)


def signaling_error_log(ctx: Ctx) -> ConditionResult:
    facts = [f for f in ctx.facts.query(FactKind.LOG_EVENT, category="signaling") if f.data.get("same_call") is not False]
    return _condition("signaling_error_log", "Có log signaling WARN/ERROR", CondState.TRUE if facts else CondState.FALSE, facts)


def answer_timeout_observed(ctx: Ctx) -> ConditionResult:
    facts = ctx.facts.query(FactKind.TRACE_TIMING, phase="offer_answer")
    return _condition("answer_timeout_observed", "Đã quan sát ANSWER timeout", CondState.TRUE if facts else CondState.UNKNOWN, facts)


def _turn(ctx: Ctx) -> str:
    facts = ctx.facts.query(FactKind.SELECTED_PATH)
    if facts and facts[0].data.get("turn_server"):
        return str(facts[0].data["turn_server"])
    # A direct path names no TURN server; the TURN metric FACT still does.
    for kind in (FactKind.METRIC_CHANGE, FactKind.METRIC_LEVEL, FactKind.MISSING_DATA):
        metric_facts = ctx.facts.query(kind, metric="turn_cpu_pct")
        if metric_facts and metric_facts[0].source:
            return metric_facts[0].source
    return "chưa rõ server"


def _path(ctx: Ctx) -> str:
    facts = ctx.facts.query(FactKind.SELECTED_PATH)
    if not facts:
        return "chưa có selected pair"
    data = facts[0].data
    return f"{data['local_type']}↔{data['remote_type']} " + (f"qua {_turn(ctx)}" if data["via_turn"] else "(trực tiếp)")


def _turn_rejection(ctx: Ctx, false: list[ConditionResult]) -> str:
    route = via_turn(ctx)
    if route.state == CondState.FALSE:
        cpu = ctx.changes(metric="turn_cpu_pct")
        cpu_part = f"TURN CPU {_turn(ctx)} có anomaly ({', '.join(f.fact_id for f in cpu)}) nhưng " if cpu else ""
        return (f"{cpu_part}selected path ({', '.join(route.fact_ids)}) là {_path(ctx)}: "
                f"TURN không nằm trên media path của cuộc gọi này.")
    cpu = turn_cpu_high_overlap(ctx)
    return f"TURN CPU {_turn(ctx)} không ghi nhận anomaly theo rule trong incident ({', '.join(cpu.fact_ids)})."


def _signaling_conclusion(ctx: Ctx) -> str:
    waited = ctx.facts.query(FactKind.TRACE_TIMING, phase="offer_answer")[0].data["duration_ms"]
    return f"Cuộc gọi thất bại ở phase Offer/Answer SDP: caller không nhận được SDP answer trong {waited} ms; ICE và Media chưa bắt đầu."


def _ice_conclusion(ctx: Ctx) -> str:
    data = ctx.facts.query(FactKind.ICE_CHECKS)[0].data
    relay = " (kể cả relay)" if data["relay_pair_failed"] else ""
    return f"Cuộc gọi thất bại ở phase ICE Candidate Exchange: {data['total']}/{data['total']} candidate pair thất bại{relay}; Media không được thiết lập."


RULES: tuple[RuleSpec, ...] = (
    RuleSpec(
        "SIGNALING_FAILURE", "Signaling failure", config.RULE_SPECIFICITY["SIGNALING_FAILURE"],
        (phase_failed(Phase.OFFER_ANSWER),), (answer_timeout_observed,),
        _signaling_conclusion, lambda ctx: "Signaling chưa hoàn tất; cần xác minh việc chuyển tiếp OFFER/ANSWER.",
        boosters=(signaling_error_log,),
        alternatives=("Callee mất kết nối tới signaling server", "Signaling server không chuyển tiếp OFFER", "Callee nhận OFFER nhưng không tạo được ANSWER"),
        unknowns=("Lý do kết nối signaling của callee bị đóng",),
        next_checks=lambda ctx: [f"Kiểm tra log signaling server cho OFFER trong {ctx.focus_window_str()}: đã chuyển tới callee chưa", "Kiểm tra trạng thái kết nối websocket của callee quanh OFFER_SENT", "Kiểm tra log phía callee (chưa thu thập trong MVP)"],
    ),
    RuleSpec(
        "ICE_CONNECTIVITY_FAILURE", "ICE failure", config.RULE_SPECIFICITY["ICE_CONNECTIVITY_FAILURE"],
        (phase_failed(Phase.ICE),), (all_pairs_failed,), _ice_conclusion,
        lambda ctx: "ICE thất bại; chưa đủ evidence để xác minh kết quả mọi candidate pair.",
        boosters=(relay_pair_attempted,),
        alternatives=("UDP bị firewall chặn ở một hoặc hai phía", "TURN server không reachable từ phía peer", "Cấu hình ICE server sai"),
        unknowns=("Loại NAT/firewall của hai phía", "Lý do relay pair thất bại"),
        next_checks=lambda ctx: ["Thử TURN qua TCP/TLS 443", "Thu error code STUN/TURN của từng candidate pair", "Kiểm tra candidate phía bob có tới được alice qua signaling không"],
    ),
    RuleSpec(
        "TURN_OVERLOAD_DEGRADATION", "TURN overload", config.RULE_SPECIFICITY["TURN_OVERLOAD_DEGRADATION"],
        (qos_incident,), (via_turn, turn_cpu_on_path_high),
        lambda ctx: f"Chất lượng cuộc gọi suy giảm trong {ctx.focus_window_str()} có khả năng liên quan tới tình trạng quá tải ở TURN server {_turn(ctx)} (đang nằm trên media path).",
        lambda ctx: f"Suy giảm chất lượng trong {ctx.focus_window_str()} có thể liên quan tới quá tải TURN server {_turn(ctx)}",
        boosters=(turn_cpu_precedes_qos, turn_logs_on_path), counters=(client_cpu_high,),
        rejection_reason=_turn_rejection,
        alternatives=("Nghẽn mạng giữa TURN và peer", "Suy giảm access network của alice hoặc bob"),
        unknowns=("Lý do TURN CPU tăng (số allocation, traffic của call khác)",),
        next_checks=lambda ctx: [f"So sánh TURN CPU với số allocation đang hoạt động và relay throughput trong {ctx.focus_window_str()}", f"Kiểm tra các call khác dùng {_turn(ctx)} trong cùng window có suy giảm không", f"Kiểm tra metric queue/drop của {_turn(ctx)}"],
    ),
    RuleSpec(
        "NETWORK_PATH_DEGRADATION", "Network degradation", config.RULE_SPECIFICITY["NETWORK_PATH_DEGRADATION"],
        (qos_incident,), (rtt_or_loss_anomaly,),
        lambda ctx: f"Media path ({_path(ctx)}) bị suy giảm trong {ctx.focus_window_str()}: {', '.join(dict.fromkeys(config.METRIC_META[f.metric]['label'] for f in ctx.changes(category='qos')))} có anomaly theo rule.",
        lambda ctx: f"Media path có thể bị suy giảm trong {ctx.focus_window_str()}",
        boosters=(multi_qos_metrics,), counters=(client_cpu_high,), missing_penalties=(turn_metrics_missing_on_relay,),
        alternatives=("Nghẽn access network (Wi-Fi/4G) của một trong hai peer", "Nghẽn ISP/routing", "Quá tải thành phần relay nếu path đi qua TURN"),
        unknowns=("Vị trí nghẽn cụ thể trên path", "Chất lượng phía bob (không có stats)"),
        next_checks=lambda ctx: [f"So sánh RTT/loss phía bob trong {ctx.focus_window_str()}", f"Chạy MTR tới địa chỉ remote candidate trong {ctx.focus_window_str()}"],
    ),
    RuleSpec(
        "RELAY_NOT_A_FAULT", "Healthy relay", config.RULE_SPECIFICITY["RELAY_NOT_A_FAULT"],
        (via_turn, no_qos_anomaly), (all_phases_ok,),
        lambda ctx: f"Cuộc gọi đi qua TURN relay ({_turn(ctx)}) và không ghi nhận QoS anomaly theo rule: việc dùng TURN không đi kèm suy giảm chất lượng được phát hiện.",
        lambda ctx: "Cần thêm evidence để xác minh toàn bộ phase của cuộc gọi relay.",
        unknowns=("Lý do direct pair không được chọn (không ảnh hưởng chất lượng cuộc gọi này)",),
    ),
    RuleSpec(
        "HEALTHY_CALL", "Healthy call", config.RULE_SPECIFICITY["HEALTHY_CALL"],
        (media_ok, no_qos_anomaly), (all_phases_ok,),
        lambda ctx: "Không phát hiện incident: 5 phase hoàn tất và không ghi nhận QoS anomaly theo rule trong phase Media.",
        lambda ctx: "Chưa đủ evidence xác minh mọi phase của cuộc gọi.",
    ),
)
