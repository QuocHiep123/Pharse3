# Gradio demo UI cho callops

Spec đã duyệt: `docs/superpowers/specs/2026-10-31-gradio-demo-design.md`.
Branch: `feat/webrtc-call-aiops-poc` (làm trực tiếp, không tạo branch mới, **không commit** — người dùng tự commit).

## Mục tiêu & tiêu chí hoàn thành

Demo Gradio giúp người mới hiểu *vì sao cuộc gọi WebRTC lỗi và cách sửa*: xem call flow từng bước (animation),
QoS theo thời gian, và mỗi INFERENCE dựa trên FACT nào. Chạy hoàn toàn bằng `InMemoryStore`, không Docker, không LLM.

Hoàn thành khi:
1. `.venv\Scripts\python -m pytest -q` pass toàn bộ (23 test cũ + test mới), không test nào cần Gradio server/Docker/LLM.
2. Cả 7 kịch bản trong `SCENARIOS` chạy qua `callops.ui.runner.run_scenario` ra `DiagnosisReport` hợp lệ; upload JSONL/CSV export ngược lại (`reanalyze`) cho cùng verdict/media_path/hypothesis.
3. `callops ui --port 7861` mở được app; 6 tab: Run/Playground, Call Flow, QoS Timeline, Diagnosis, Logs/Export, Upload/Re-analyze. Chế độ "Giải thích cho người mới" bật mặc định.
4. File sai định dạng → cảnh báo trong UI (`UiInputError`), không crash; không có sự kiện → thông báo rỗng.
5. Có ảnh chụp màn hình từng tab (browser-automation), console trình duyệt không có lỗi JS.
6. **Không** sửa `models.py`, `qos.py`, `storage.py` (SHARED), cũng không sửa `diagnosis.py`, `simulator.py`, `scenarios.py`.

## Thiết kế (quyết định chính + lý do)

**D1. Interface chung tách ra `src/callops/ui/contracts.py` (T1) thay vì để trong `runner.py`/`flow.py` như spec.**
Phương án A: theo spec, `RunResult` ở runner, `FlowStep` ở flow → flow/charts/views phải chờ runner. Phương án B: một module
contract nhỏ làm trước, mọi task khác chỉ import từ đó → 5 task song song. Chọn B. `runner.py` và `flow.py` re-export
`RunResult` / `FlowStep` để giữ đúng tên trong spec (`from callops.ui.runner import RunResult` vẫn chạy).

**D2. Chẩn đoán vẫn đi qua `DiagnosisService` (đường code chính thức), rule trace chạy lại riêng.**
Spec yêu cầu "rule không khớp và lý do" + "INFERENCE nào do rule nào". `InferenceEngine.infer()` không trả về tên rule.
Phương án A: tự viết lại verdict logic + gọi từng rule → trùng lặp logic `DiagnosisService`. Phương án B: report lấy từ
`DiagnosisService.diagnose()` (giữ validator + verdict gốc); runner chạy thêm `FactExtractor().extract()` + lặp
`InferenceEngine().rules` trên cùng dữ liệu để biết rule → inference id. Extractor/engine tất định (đếm id từ 1) nên id
trùng khớp — có test khẳng định. Chọn B. Chi phí chạy 2 lần không đáng kể.

**D3. Upload đi qua `InMemoryStore` rồi `DiagnosisService`.** `reanalyze` index event/sample vào store mới và tự suy ra call state
(`state` = state của event cuối; `media_path` = `detail["media_path"]` của event cuối có key này, chỉ nhận giá trị hợp lệ của `MediaPath`).
Dữ liệu không đủ để dựng report (vd. `healthy_call` khớp nhưng không có FACT nào → `Inference(derived_from=[])` lỗi) →
bắt `pydantic.ValidationError` và ném `UiInputError` — **không nới validator**.

**D4. Trục thời gian chung = giây kể từ `RunResult.t0`** (ts sớm nhất trong events ∪ samples). Flow (`FlowStep.t`) và chart (trục x)
cùng dùng trục này nên 1 thanh trượt thời gian (giây) đồng bộ được cả hai. `Window.start_s/end_s` (tính theo `t_s` của media) được chart
quy đổi sang trục chung.

**D5. Thanh trượt thời gian đặt một lần, ngay trên `gr.Tabs`** (hiện khi đã có kết quả), điều khiển cả SVG flow lẫn vạch cursor trên chart.
Tránh 2 slider đồng bộ chéo gây vòng lặp sự kiện. Play/Pause bằng `gr.Timer` (mỗi tick +1s).

**D6. Logic hiển thị thuần (markdown/HTML) nằm ở `views.py`, `app.py` chỉ nối Gradio.** Test được views không cần Gradio.

**D7. Giải thích sự kiện call flow nằm trong `flow.py`; glossary thuật ngữ + giải thích rule nằm trong `explain.py`.**
Để flow và explain làm song song không phụ thuộc nhau. Mọi con số ngưỡng trong text giải thích phải format từ `THRESHOLDS`, không hard-code.

**D8. JSONL upload = định dạng document `callops-events`** (mỗi dòng 1 `CallEvent.model_dump(mode="json")`, chính là file tab Export sinh ra).
File `logs/run-*.jsonl` của `logging_setup` thiếu `call_id`/`state`/ts đầy đủ nên không dựng lại được `CallEvent` → nhận diện
(dòng có `@timestamp` + `logger`) và báo lỗi có hướng dẫn. (Xem Câu hỏi mở Q1.)

**D9. Log console của simulator/diagnosis được bắt vào `RunResult.log_lines`** bằng handler tạm gắn vào logger `callops` (level DEBUG, khôi phục
level/handler cũ sau khi chạy). Tab Logs hiển thị như terminal. Không gọi `setup_logging` (không ghi file `logs/` từ UI).

**FACT vs INFERENCE trong UI**: UI chỉ hiển thị, không tạo FACT/INFERENCE. INFERENCE luôn hiển thị nhãn "giả thuyết", confidence,
và danh sách `[Fxx]` trích dẫn. "Lý do rule không khớp" là mô tả tĩnh điều kiện tiên quyết của rule (trong `explain.RULE_EXPLAIN`),
không phải khẳng định chẩn đoán.

### Sơ đồ module

```
contracts.py (T1)  <-- runner (T2), loaders (T3), flow (T4), charts (T5, chỉ cần Window), explain (T6, không cần)
views.py (T7)      <-- contracts, explain, flow(FlowStep)
app.py (T8)        <-- tất cả; cli.py `callops ui` import app lười (lazy)
```

### Interface chốt ở T1 (mọi task khác dựa vào đúng chữ ký này)

```python
# src/callops/ui/contracts.py
class UiInputError(ValueError): ...            # thông điệp tiếng Việt, hiển thị thẳng trong UI

STEP_TITLES_VI: dict[int, str]                 # 1..6 khớp README: 1 CALL SETUP, 2 SDP OFFER/ANSWER, 3 ICE GATHERING,
                                               # 4 ICE CHECKS, 5 MEDIA, 6 TERMINATION

@dataclass(frozen=True)
class FlowStep:
    seq: int            # thứ tự 1..N trong timeline
    step_no: int        # bước call flow 1..6 (STEP_TITLES_VI)
    t: float            # giây kể từ t0
    actor_from: str
    actor_to: str
    event: str          # tên event gốc, vd "SDP_OFFER"
    title: str          # tiêu đề ngắn tiếng Việt
    message: str        # CallEvent.message gốc
    explain_vi: str     # giải thích cho người mới
    log_ref: str        # f"{event} @ {ts.isoformat()}"
    level: str = "INFO"
    @property
    def is_problem(self) -> bool: ...   # level in {"WARNING","ERROR","CRITICAL"}

@dataclass(frozen=True)
class RuleTrace:
    rule: str                        # tên rule trong InferenceEngine().rules
    inference_ids: tuple[str, ...]   # rỗng = không khớp
    @property
    def matched(self) -> bool: ...

@dataclass(frozen=True)
class RunResult:
    scenario_name: str
    source: Literal["simulated", "uploaded"]
    call_id: str
    events: tuple[CallEvent, ...]       # sort theo ts
    samples: tuple[QoSSample, ...]      # sort theo (ts, participant_id)
    report: DiagnosisReport
    windows: tuple[Window, ...]         # callops.diagnosis.Window
    rule_traces: tuple[RuleTrace, ...]
    scenario: Scenario | None = None    # None khi upload
    log_lines: tuple[str, ...] = ()
    @property
    def facts(self) -> list[Fact]: ...              # = report.facts
    @property
    def t0(self) -> datetime | None: ...            # min ts của events ∪ samples; None nếu cả hai rỗng
    def rel_t(self, ts: datetime) -> float: ...     # (ts - t0).total_seconds(); 0.0 nếu t0 None
    @property
    def duration_s(self) -> float: ...              # max rel_t trên events ∪ samples (sample cộng thêm 1s); 0.0 nếu rỗng
    def inference(self, inf_id: str) -> Inference: ...   # KeyError nếu không có
    def cited_facts(self, inf_id: str) -> list[Fact]: ... # theo thứ tự derived_from
    def rule_of(self, inf_id: str) -> str | None: ...
```

## Câu hỏi mở

- **Q1 (D8)** Upload JSONL: chỉ nhận định dạng event export (`callops-events`), từ chối `logs/run-*.jsonl` kèm hướng dẫn. Có cần parse cả log JSONL của logging không? (Hiện log đó thiếu `call_id`, `state`, ngày của ts → sẽ phải đổi `simulator._emit`, ngoài phạm vi.)
- **Q2** Upload chứa nhiều `call_id`: plan hiện báo `UiInputError` liệt kê các id. Có muốn thay bằng dropdown chọn call không?
- **Q3** Spec ghi `gradio>=4`, nhưng app viết và kiểm trên Gradio 6.31 (vd. `css`/`theme` truyền ở `launch()`, `gr.Timer`). Đề xuất đổi extra thành `gradio>=6` cho trung thực. Plan đang giữ `gradio>=4` theo spec, chờ người dùng chốt.
- **Q4** Ảnh chụp màn hình T9 lưu vào `docs/screenshots/2026-10-31-gradio/` (commit vào repo) hay chỉ để ngoài repo?
- **Q5** Owner: UI không có trong bảng phân vai. Plan gán **hiepdq**; đề xuất doandd review `charts.py` + `loaders.py` (mảng data). Có đúng không?

## Task list

Thứ tự đợt chạy:

| Đợt | Task | Song song |
|---|---|---|
| 0 | T1 contracts | — (nhỏ, làm trước) |
| 1 | T2 runner · T3 loaders · T4 flow · T5 charts · T6 explain | 5 coder song song |
| 2 | T7 views | — (cần T2, T6) |
| 3 | T8 app + `callops ui` + extra `ui` + README | — (cần tất cả) |
| 4 | T9 smoke test + screenshot | — |

Quy ước chung cho mọi task:
- Mỗi task **chỉ tạo/sửa đúng file trong mục Files**. Không tạo `tests/conftest.py`, không sửa `src/callops/ui/__init__.py` (của T1). Fixture dùng riêng trong file test của mình.
- Import tuyệt đối (`from callops.ui.contracts import ...`). Comment tiếng Việt ngắn, type hint đầy đủ, `from __future__ import annotations`.
- Module cần thư viện extra (`plotly`, `yaml`, `gradio`) thì test đầu file dùng `pytest.importorskip("<lib>")`. `yaml` import lười trong hàm.
- Khi đang chạy song song (đợt 1), chạy `python -m pytest tests/test_<file của mình>.py tests/test_flow.py tests/test_qos.py -q`; test file của coder khác có thể đang dở. Cuối đợt người điều phối chạy toàn bộ `python -m pytest -q`.
- Test không được cần Gradio server, Docker, LLM, mạng.
- Không commit.

---

### T1: Contracts nền cho package `callops.ui`  [owner: hiepdq] [depends: -] [parallel-safe: no — phải xong trước đợt 1]
- Files: `src/callops/ui/__init__.py` (tạo), `src/callops/ui/contracts.py` (tạo), `tests/test_ui_contracts.py` (tạo)
- Skill cần gọi: `callops-domain`, `grounded-diagnosis`, `superpowers:test-driven-development`
- Việc cần làm:
  - `__init__.py`: docstring mô tả package (Gradio demo, chạy bằng InMemoryStore). Chỉ re-export từ `contracts`: `RunResult`, `FlowStep`, `RuleTrace`, `UiInputError`, `STEP_TITLES_VI`. **Không** import gradio/plotly/yaml ở đây (import `callops.ui.runner` phải chạy được khi chưa cài extra `ui`).
  - `contracts.py`: đúng chữ ký ở mục "Interface chốt ở T1" phía trên. Chi tiết:
    - `UiInputError(ValueError)` với docstring.
    - `STEP_TITLES_VI = {1: "Thiết lập cuộc gọi (signaling)", 2: "Trao đổi SDP offer/answer", 3: "ICE gathering (host/srflx/relay)", 4: "ICE connectivity checks", 5: "Media + đo QoS", 6: "Kết thúc cuộc gọi"}`.
    - `FlowStep`, `RuleTrace`, `RunResult` là `@dataclass(frozen=True)`; `Window` import từ `callops.diagnosis`; `CallEvent`, `QoSSample`, `DiagnosisReport`, `Fact`, `Inference` từ `callops.models`; `Scenario` từ `callops.scenarios`.
    - `RunResult.t0`: min của `e.ts` và `s.ts`. `duration_s`: max(`rel_t(e.ts)` cho events, `rel_t(s.ts) + 1` cho samples), 0.0 nếu rỗng.
    - `cited_facts(inf_id)`: map id → Fact, trả theo thứ tự `derived_from`.
    - `rule_of(inf_id)`: rule đầu tiên trong `rule_traces` có `inf_id` trong `inference_ids`, không có → None.
- Test phải viết (`tests/test_ui_contracts.py`, dựng dữ liệu bằng tay, không chạy simulator):
  - Helper tạo 2 `CallEvent` (ts 09:00:00Z và 09:00:02Z), 2 `QoSSample` (ts 09:00:01Z, 09:00:05Z), report với F01, F02 và I01 (`derived_from=["F02","F01"]`), `rule_traces=(RuleTrace("r_a", ("I01",)), RuleTrace("r_b", ()))`.
  - `t0` == 09:00:00Z; `rel_t(09:00:02Z)` == 2.0; `duration_s` == 6.0 (sample cuối 5s + 1).
  - `cited_facts("I01")` trả [F02, F01] đúng thứ tự; `inference("I99")` → `KeyError`.
  - `rule_of("I01") == "r_a"`; `rule_of("I99") is None`; `RuleTrace("r_b", ()).matched is False`.
  - Gán thuộc tính vào `RunResult` → `dataclasses.FrozenInstanceError`.
  - `RunResult` với events=(), samples=() → `t0 is None`, `duration_s == 0.0`, `rel_t(...) == 0.0`.
  - `issubclass(UiInputError, ValueError)`; `FlowStep(..., level="ERROR").is_problem` True, `"INFO"` False.
  - `set(STEP_TITLES_VI) == {1,2,3,4,5,6}`.
- Done khi: `python -m pytest tests/test_ui_contracts.py -q` pass + toàn bộ `python -m pytest -q` pass.
- Commit: `feat(ui): add shared contracts for gradio demo`

---

### T2: Runner — chạy scenario / re-analyze ra RunResult  [owner: hiepdq] [depends: T1] [parallel-safe: yes]
- Files: `src/callops/ui/runner.py` (tạo), `tests/test_ui_runner.py` (tạo)
- Skill cần gọi: `callops-domain`, `grounded-diagnosis`, `superpowers:test-driven-development`
- Việc cần làm (dùng API có sẵn: `CallSimulator(scenario, store, seed).run()` → `CallResult.call_id`; `DiagnosisService(store).diagnose(call_id, scenario_name)`; `store.search(EVENTS_INDEX|QOS_INDEX, call_id)`; `FactExtractor().extract(events_dicts, samples)` → `FactBundle(.facts, .windows)`; `InferenceEngine().rules` là `list[tuple[str, Rule]]`, gọi `rule(bundle)`):
  - Re-export: `from callops.ui.contracts import RunResult, RuleTrace, UiInputError` (`__all__`).
  - `DEFAULT_SEED: int = 42` (bằng `Settings.seed` mặc định).
  - `@contextmanager def capture_logs(level: int = logging.DEBUG) -> Iterator[list[str]]`: gắn `logging.Handler` tạm vào `logging.getLogger("callops")`, set level `level`, mỗi record → chuỗi `f"{levelname:<7} {name.removeprefix('callops.'):<10} | {getMessage()}"` (không mã màu ANSI); `finally` gỡ handler + khôi phục level cũ.
  - `def run_scenario(scenario: Scenario, seed: int = DEFAULT_SEED) -> RunResult`: `InMemoryStore()` mới → simulator → diagnose → đọc events (`CallEvent.model_validate`) + samples (`QoSSample.model_validate`) từ store → `_trace(...)` → `RunResult(source="simulated", scenario=scenario, scenario_name=scenario.name, log_lines=...)`. Toàn bộ chạy trong `capture_logs()`.
  - `def reanalyze(events: Sequence[CallEvent], samples: Sequence[QoSSample], *, scenario_name: str = "uploaded") -> RunResult`:
    - Cả hai rỗng → `UiInputError("Không có sự kiện hay mẫu QoS nào để phân tích")`.
    - Tập `call_id` (events ∪ samples) > 1 → `UiInputError` liệt kê các id (sorted).
    - Index vào `InMemoryStore` mới bằng `model_dump(mode="json")`; `store.set_call_state(call_id, _derive_call_state(events))`.
    - Gọi `DiagnosisService(store).diagnose(call_id, scenario_name)`; bắt `pydantic.ValidationError` → `UiInputError("Dữ liệu không đủ để dựng báo cáo chẩn đoán: ...")` (`raise ... from exc`). **Không** sửa/nới validator.
    - `source="uploaded"`, `scenario=None`.
  - `def _derive_call_state(events: Sequence[CallEvent]) -> dict[str, str]`: `{"state": events[-1].state.value}` (sau khi sort theo ts) nếu có event; thêm `"media_path"` = `detail["media_path"]` của event cuối có key đó **nếu** giá trị thuộc `{m.value for m in MediaPath}`.
  - `def _trace(events_dicts: list[dict[str, Any]], samples: list[QoSSample]) -> tuple[tuple[Window, ...], tuple[RuleTrace, ...]]`: `bundle = FactExtractor().extract(...)`; `engine = InferenceEngine()`; với mỗi `(name, rule)` trong `engine.rules`: `res = rule(bundle)` → `RuleTrace(name, tuple(i.id for i in res))`. (Engine mới → id I01.. trùng với report.)
    - **Thứ tự bắt buộc**: gọi `diagnose()` trước, chỉ chạy `_trace` khi diagnose thành công (dữ liệu thiếu FACT làm rule `healthy_call` ném `ValidationError` ở cả hai nơi). Bọc `_trace` trong cùng khối bắt `ValidationError` → `UiInputError`.
  - Sort `events` theo ts, `samples` theo `(ts, participant_id)` trước khi đóng gói.
- Test phải viết (`tests/test_ui_runner.py`):
  - `@pytest.mark.parametrize("name", sorted(SCENARIOS))`: `r = run_scenario(SCENARIOS[name])` → `r.source == "simulated"`, `r.scenario is SCENARIOS[name]`, `r.report.inferences` không rỗng, mọi `derived_from ⊆ {f.id}`; `[t.rule for t in r.rule_traces] == [n for n, _ in InferenceEngine().rules]`; flatten `inference_ids` == `[i.id for i in r.report.inferences]`; `{w.fact_id for w in r.windows} ⊆ fact ids`; events sort tăng dần theo ts.
  - Bảng verdict/media_path giống `tests/test_flow.py::test_scenario_path_and_verdict` (vd. `congestion` → P2P_STUN/CRITICAL, `ice_failed_no_turn` → None/CRITICAL).
  - Tất định: chạy `run_scenario(SCENARIOS["congestion"], seed=42)` 2 lần → cùng `call_id` và cùng list `f.statement`.
  - `r.log_lines` không rỗng và có dòng chứa `"[STEP 1]"`; sau khi chạy `logging.getLogger("callops").level` bằng giá trị trước khi chạy và số handler không đổi.
  - Round-trip: `r = run_scenario(SCENARIOS[n])`, `r2 = reanalyze(r.events, r.samples)` với n ∈ {congestion, ice_failed_no_turn, group_sfu} → cùng `verdict`, `media_path`, list `hypothesis`; `r2.source == "uploaded"`, `r2.scenario is None`.
  - `reanalyze([], [])` → `UiInputError`.
  - Đổi `call_id` của 1 event (`ev.model_copy(update={"call_id": "other"})`) → `UiInputError`, message chứa `"other"`.
  - Chỉ 1 event `INVITE` (lấy từ run p2p_good), samples rỗng → `UiInputError` (không phải `ValidationError`).
  - `_derive_call_state` với event có `detail={"media_path": "BOGUS"}` → không có key `media_path`.
- Done khi: `python -m pytest tests/test_ui_runner.py tests/test_flow.py -q` pass.
- Commit: `feat(ui): add scenario runner and re-analyze with rule trace`

---

### T3: Loaders — đọc/ghi JSONL, CSV, scenario YAML/JSON  [owner: hiepdq, review: doandd] [depends: T1] [parallel-safe: yes]
- Files: `src/callops/ui/loaders.py` (tạo), `tests/test_ui_loaders.py` (tạo)
- Skill cần gọi: `callops-domain`, `python-error-handling`, `superpowers:test-driven-development`
- Việc cần làm (mọi lỗi → `UiInputError` thông điệp tiếng Việt, có tên file + số dòng khi liên quan; dùng `raise ... from exc`):
  - `QOS_CSV_COLUMNS: tuple[str, ...] = tuple(QoSSample.model_fields)`.
  - `def load_jsonl(path: str | Path) -> list[CallEvent]`: đọc UTF-8 (`utf-8-sig` để chịu BOM), bỏ dòng trống. File không tồn tại → "Không tìm thấy file ..."; không còn dòng nào → "File rỗng ...". Dòng không phải JSON → "Dòng {n}: không phải JSON hợp lệ". Dòng có cả `"@timestamp"` và `"logger"` → thông điệp riêng: đây là log JSONL của logging (`logs/run-*.jsonl`), không phải event export; hãy dùng file export ở tab Logs/Export. `ValidationError` → "Dòng {n}: thiếu/sai trường: {loc1, loc2}" (gom `err["loc"]`).
  - `def load_qos_csv(path: str | Path) -> list[QoSSample]`: dùng `csv.DictReader` (stdlib, không pandas), encoding `utf-8-sig`. Thiếu cột → "Thiếu cột: a, b" (theo thứ tự `QOS_CSV_COLUMNS`); cột thừa bỏ qua; không có dòng dữ liệu → "File rỗng"; giá trị sai → "Dòng {n}: ..." (n tính cả header, dòng dữ liệu đầu = 2).
  - `def parse_scenario_text(text: str, *, source: str = "<text>") -> Scenario`: thử `json.loads`; nếu lỗi JSON thì `yaml.safe_load` (import lười; `ImportError` → UiInputError "Cần cài extra ui: pip install -e .[ui]"). Text rỗng / kết quả không phải dict → UiInputError. `ValidationError` → liệt kê `loc` + `msg`.
  - `def load_scenario(path: str | Path) -> Scenario`: đuôi `.yaml/.yml/.json` (không phân biệt hoa thường), đuôi khác → UiInputError "Chỉ hỗ trợ .yaml, .yml, .json"; đọc text rồi gọi `parse_scenario_text(text, source=path.name)`.
  - `def scenario_to_yaml(scenario: Scenario) -> str`: `yaml.safe_dump(scenario.model_dump(mode="json"), allow_unicode=True, sort_keys=False)`.
  - `def dump_events_jsonl(events: Iterable[CallEvent], path: str | Path) -> Path`: mỗi dòng `ev.model_dump_json()` (giữ tiếng Việt: dùng `json.dumps(ev.model_dump(mode="json"), ensure_ascii=False)`), UTF-8, trả `Path`.
  - `def dump_qos_csv(samples: Iterable[QoSSample], path: str | Path) -> Path`: header `QOS_CSV_COLUMNS`, giá trị từ `model_dump(mode="json")`.
- Test phải viết (`tests/test_ui_loaders.py`, dùng `tmp_path`; dữ liệu thật lấy bằng `CallSimulator(SCENARIOS["congestion"], InMemoryStore(), seed=42).run()` + `store.search(...)` — **không** import `callops.ui.runner` vì T2 chạy song song):
  - Round-trip: `dump_events_jsonl` → `load_jsonl` == list event gốc (so sánh `model_dump()`); `dump_qos_csv` → `load_qos_csv` == samples gốc.
  - `load_jsonl` file không tồn tại / file chỉ có dòng trắng / dòng `{not json` / dòng thiếu `call_id` / dòng `{"@timestamp": "...", "logger": "callops.call", "message": "x"}` → `UiInputError`, message lần lượt chứa "Không tìm thấy", "rỗng", "Dòng 1", "call_id", "logs/run".
  - `load_qos_csv` thiếu cột `mos` và `rtt_ms` → message chứa "rtt_ms" và "mos"; `rtt_ms=abc` ở dòng dữ liệu đầu → message chứa "Dòng 2"; file có BOM vẫn đọc được.
  - `scenario_to_yaml(SCENARIOS["group_sfu"])` → `parse_scenario_text(...)` == scenario gốc (so `model_dump()`); JSON text cũng parse được; `load_scenario` với `.yaml` và `.json` trong tmp_path đều ra `Scenario`.
  - `parse_scenario_text("name: x\nparticipants: []")` → UiInputError (min_length=2); `"- a\n- b"` (list) → UiInputError; `""` → UiInputError; `load_scenario("x.txt")` → UiInputError chứa ".yaml".
  - Đầu file test: `pytest.importorskip("yaml")` chỉ cho các test YAML (dùng marker/skip theo hàm, để test JSONL/CSV vẫn chạy khi không có yaml).
- Done khi: `python -m pytest tests/test_ui_loaders.py -q` pass.
- Commit: `feat(ui): add jsonl/csv/scenario loaders with clear input errors`

---

### T4: Flow — timeline các bước + SVG sequence diagram có animation  [owner: hiepdq] [depends: T1] [parallel-safe: yes]
- Files: `src/callops/ui/flow.py` (tạo), `tests/test_ui_flow.py` (tạo)
- Skill cần gọi: `callops-domain`, `frontend-design:frontend-design` (thẩm mỹ SVG), `superpowers:test-driven-development`
- Việc cần làm:
  - Re-export `FlowStep` từ contracts.
  - `INFRA_ACTORS: tuple[str, ...] = ("Signaling", "STUN", "TURN", "SFU")`.
  - `EVENT_INFO: dict[str, tuple[int, str, str]]` — event → (step_no, title_vi, explain_vi). Phủ đủ các event simulator phát ra (xem `simulator.py`): `INVITE`, `JOIN_ROOM`, `RINGING_ACCEPTED` → 1; `SDP_OFFER`, `SDP_ANSWER` → 2; `STUN_TIMEOUT`, `ICE_GATHERING_COMPLETE` → 3; `ICE_CANDIDATES_EXCHANGED`, `TURN_FALLBACK`, `ICE_SELECTED_PAIR`, `ICE_FAILED`, `SFU_CONNECTED` → 4; `MEDIA_ESTABLISHED`, `QOS_ALERT`, `QOS_RECOVERED` → 5; `BYE`, `CALL_FAILED` → 6. `explain_vi` 1–3 câu cho người mới (vd. SDP_OFFER: "Caller mô tả mình muốn gửi gì (codec opus/VP8, BUNDLE) trong SDP và gửi qua signaling server; chưa có media nào chảy."). Không ghi con số ngưỡng QoS cứng (QOS_ALERT chỉ nói "vượt ngưỡng trong THRESHOLDS", message gốc đã có giá trị).
  - Event lạ: step_no theo `CallState` (`IDLE/SETUP`→1, `OFFER_SENT/ANSWER_RECEIVED`→2, `ICE_CHECKING`→4, `CONNECTED`→5, `TERMINATED/FAILED`→6), title = tên event, explain chung.
  - `def build_timeline(events: Sequence[CallEvent], t0: datetime | None = None) -> list[FlowStep]`: sort theo ts; `t0` mặc định = ts event đầu; `seq` từ 1. Xác định actor:
    - `caller` = `detail["caller"]` của `INVITE`/`JOIN_ROOM` đầu tiên, không có → "Caller"; `callees` = các `detail["callee"]` của `RINGING_ACCEPTED`; `peer` = callee đầu tiên, không có → "Peer". `p` = `detail.get("participant", caller)`.
    - Bảng from→to: `INVITE`/`JOIN_ROOM`/`SDP_OFFER`/`ICE_CANDIDATES_EXCHANGED`/`BYE`/`CALL_FAILED`: caller→Signaling; `RINGING_ACCEPTED`: callee→Signaling; `SDP_ANSWER`: Signaling→caller; `STUN_TIMEOUT`: p→STUN; `ICE_GATHERING_COMPLETE`: p→TURN nếu `"relay"` trong `detail["candidate_types"]` ngược lại p→STUN; `TURN_FALLBACK`: p→TURN; `SFU_CONNECTED`: p→SFU; `ICE_FAILED`: p→SFU nếu có `participant` trong detail, ngược lại caller→peer; `ICE_SELECTED_PAIR`/`MEDIA_ESTABLISHED`: theo `detail["media_path"]`: `SFU`→caller→SFU, `TURN_RELAY`→caller→TURN, khác → caller→peer (ghi nhớ media target hiện tại); `QOS_ALERT`/`QOS_RECOVERED`: p→media target hiện tại (mặc định peer; nếu p == peer thì target = caller); lạ: caller→Signaling.
    - `log_ref = f"{ev.event} @ {ev.ts.isoformat()}"`, `message = ev.message`, `level = ev.level`.
  - `def actors_of(steps: Sequence[FlowStep]) -> list[str]`: participant theo thứ tự xuất hiện, sau đó các `INFRA_ACTORS` có dùng (theo thứ tự tuple).
  - `def steps_until(steps: Sequence[FlowStep], t: float) -> int`: số bước có `step.t <= t`.
  - `def render_flow_svg(steps: Sequence[FlowStep], upto: int | None = None) -> str`: `upto=None` → tất cả; kẹp về [0, len]. Trả chuỗi `<div class="callops-flow-wrap" style="max-height:620px;overflow:auto">` + `<svg id="callops-flow" ...>` gồm `<style>` nội tuyến (không `<script>`): hộp actor + lifeline nét đứt; band nhãn "STEP n · {STEP_TITLES_VI[n]}" khi step_no đổi; mỗi bước đã hiện là `<g class="step [problem] [current]" data-seq="{seq}">` chứa mũi tên (marker arrowhead; self-arrow nếu from == to) + nhãn `"{seq}. {title}"` + thời gian `t`; bước cuối (`upto`) có class `current` với CSS keyframes vẽ mũi tên (stroke-dashoffset) + nhấp nháy; bước `is_problem` màu đỏ/cam. Mọi text qua `html.escape`. `steps` rỗng → SVG nhỏ với text "Không có sự kiện nào để hiển thị". Hỗ trợ dark/light: màu chữ dùng `currentColor`.
- Test phải viết (`tests/test_ui_flow.py`; events lấy bằng `CallSimulator(..., InMemoryStore(), seed=42).run()` + `CallEvent.model_validate(d) for d in store.search(EVENTS_INDEX, call_id)` — không import runner):
  - `p2p_good`: `len(steps) == len(events)`; `seq` = 1..N; `t` không giảm; `step_no` không giảm; bước đầu `event == "INVITE"`, `actor_from == "alice"`, `actor_to == "Signaling"`; bước cuối `BYE`.
  - Mọi event trong 7 kịch bản đều có trong `EVENT_INFO` (khẳng định phủ đủ).
  - `symmetric_nat_turn`: có bước `TURN_FALLBACK` với `actor_to == "TURN"`; `MEDIA_ESTABLISHED` `actor_to == "TURN"`.
  - `group_sfu`: `actors_of` chứa alice, bob, carol, dave, "SFU"; bước `SFU_CONNECTED` của carol `actor_from == "carol"`.
  - `ice_failed_no_turn`: có bước `ICE_FAILED` `is_problem`; không có bước step_no 5.
  - `render_flow_svg(steps, upto=3)`: chứa `"<svg"`, đếm `'class="step'` == 3, chứa tên mọi actor, có đúng 1 `current`; `upto=0` → không có `class="step`; `upto=999` → == len(steps); không chứa `"<script"`.
  - Escape: FlowStep tự tạo với `title="<b>x</b>"` → output chứa `"&lt;b&gt;"`, không chứa `"<b>x</b>"`.
  - `render_flow_svg([])` chứa "Không có sự kiện".
  - `steps_until(steps, -1) == 0`; `steps_until(steps, 1e9) == len(steps)`.
  - Event lạ (`event="CUSTOM_X"`, `state=CONNECTED`) → step_no 5, title "CUSTOM_X".
- Done khi: `python -m pytest tests/test_ui_flow.py -q` pass.
- Commit: `feat(ui): add call flow timeline and animated svg sequence diagram`

---

### T5: Charts — QoS timeline Plotly  [owner: hiepdq, review: doandd] [depends: T1 (chỉ cần `callops.diagnosis.Window`)] [parallel-safe: yes]
- Files: `src/callops/ui/charts.py` (tạo), `tests/test_ui_charts.py` (tạo)
- Skill cần gọi: `callops-domain`, `dataviz` (đọc trước khi viết chart), `timeseries-anomaly-xai`, `superpowers:test-driven-development`; tra API Plotly 7 bằng `context7` nếu không chắc (`make_subplots`, `add_hline/add_vrect/add_vline` với `row`/`col`).
- Việc cần làm:
  - `METRICS: tuple[tuple[str, str], ...] = (("rtt_ms", "RTT (ms)"), ("jitter_ms", "Jitter (ms)"), ("packet_loss_pct", "Packet loss (%)"), ("mos", "MOS"))`.
  - `def qos_figure(samples: Sequence[QoSSample], thresholds: Mapping[str, Threshold] = THRESHOLDS, windows: Sequence[Window] = (), *, t0: datetime | None = None, cursor_t: float | None = None) -> go.Figure`:
    - `samples` rỗng → `go.Figure()` không trace, 1 annotation "Không có dữ liệu QoS (cuộc gọi không thiết lập được media)".
    - `make_subplots(rows=4, cols=1, shared_xaxes=True, subplot_titles=[label ...], vertical_spacing≈0.06)`.
    - x = `(s.ts - t0).total_seconds()`, `t0` mặc định = min sample ts. Mỗi participant (sorted) × metric: 1 `go.Scatter(mode="lines", name=pid, legendgroup=pid, showlegend=(row == 1))`, màu cố định theo participant (palette categorical từ skill `dataviz`), `hovertemplate` có giá trị + đơn vị. Tổng trace = 4 × số participant.
    - Ngưỡng: với mỗi metric có trong `thresholds`, `add_hline(y=th.warning, ...)` (nét đứt, màu cảnh báo) và `add_hline(y=th.critical, ...)` (màu nghiêm trọng), annotation "warn"/"crit". Lấy giá trị từ tham số `thresholds` — **không hard-code**.
    - Vùng sự cố: mỗi `Window` có `metric` thuộc `METRICS` → `add_vrect` trên đúng row của metric; x0 = `media_start(participant) + start_s`, x1 = `media_start + end_s + 1`, với `media_start = rel(first_sample_of_participant.ts) - first_sample.t_s`; màu theo `severity` (WARNING/CRITICAL), opacity ~0.15, `annotation_text = window.fact_id` (liên kết chart ↔ FACT). Window của participant không có sample → bỏ qua.
    - `cursor_t` không None → `add_vline(x=cursor_t, row="all", col=1)`.
    - Layout: `template="plotly_white"`, `height=820`, legend ngang trên cùng, `xaxis4.title = "giây kể từ bắt đầu cuộc gọi"`, `hovermode="x unified"`.
- Test phải viết (`tests/test_ui_charts.py`, `pytest.importorskip("plotly")`; dữ liệu: `CallSimulator(SCENARIOS[n], store, seed=42).run()` → samples từ `store.search(QOS_INDEX, ...)`, windows = `FactExtractor().extract(events, samples).windows` — không import runner):
  - `congestion`: `len(fig.data) == 8`; `{tr.name for tr in fig.data} == {"alice", "bob"}`; số hline (shape `type == "line"` và `y0 == y1` và `xref` kiểu paper/domain) == 8.
  - Số `vrect` (shape `type == "rect"`) == số window có metric ∈ METRICS; có vrect với x0 ≥ 10 (bob nghẽn từ t_s=10, cộng offset media).
  - `group_sfu`: `len(fig.data) == 16`.
  - Ngưỡng tùy biến: truyền `{"rtt_ms": Threshold(111, 222), ...}` (copy `THRESHOLDS` rồi thay rtt) → có hline y == 111 và y == 222.
  - `cursor_t=12.5` → có shape line `x0 == x1 == 12.5`.
  - `qos_figure([])` → `len(fig.data) == 0`, annotation chứa "Không có dữ liệu".
  - `t0` truyền sớm hơn 5s so với sample đầu → x của điểm đầu tiên == 5.0.
- Done khi: `python -m pytest tests/test_ui_charts.py -q` pass.
- Commit: `feat(ui): add plotly qos timeline with thresholds and incident windows`

---

### T6: Explain — glossary tiếng Việt + giải thích rule/verdict/metric  [owner: hiepdq] [depends: T1 (không import gì của ui)] [parallel-safe: yes]
- Files: `src/callops/ui/explain.py` (tạo), `tests/test_ui_explain.py` (tạo)
- Skill cần gọi: `callops-domain`, `grounded-diagnosis`, `superpowers:test-driven-development`
- Việc cần làm (nội dung tiếng Việt ngắn gọn, chính xác theo `callops-domain`; không hard-code số ngưỡng):
  - `@dataclass(frozen=True) class Term: key: str; name: str; short_vi: str; long_vi: str; aliases: tuple[str, ...] = ()`.
  - `GLOSSARY: dict[str, Term]` tối thiểu các key: `ICE`, `STUN`, `TURN`, `SFU`, `NAT`, `SYMMETRIC_NAT` (aliases: "NAT đối xứng", "SYMMETRIC"), `SDP`, `SIGNALING`, `CANDIDATE`, `HOST`, `SRFLX`, `RELAY`, `DTLS_SRTP`, `RTT`, `JITTER`, `PACKET_LOSS` (aliases "loss", "mất gói"), `MOS`, `CONCEALMENT` (alias "PLC"), `BUFFERBLOAT`, `FEC`, `SIMULCAST`, `FACT`, `INFERENCE`.
  - `def find_terms(text: str) -> list[Term]`: tìm `name`/`key`/`aliases` không phân biệt hoa thường, có ranh giới từ (regex `(?<!\w)...(?!\w)`, chạy được với chữ có dấu); trả theo vị trí xuất hiện đầu tiên, không trùng; khi nhiều term chồng nhau ưu tiên chuỗi dài hơn ("NAT đối xứng" → `SYMMETRIC_NAT`, không thêm `NAT` cho đúng đoạn đó).
  - `def glossary_markdown(keys: Iterable[str] | None = None) -> str`: bảng/list markdown "**name** — short_vi"; `None` → toàn bộ.
  - `@dataclass(frozen=True) class RuleExplain: title_vi: str; when_vi: str` — `when_vi` = điều kiện tiên quyết để rule khớp (dùng làm "lý do không khớp").
  - `RULE_EXPLAIN: dict[str, RuleExplain]` cho đúng 7 tên rule trong `InferenceEngine().rules`: `ice_failure_root_cause` (cần FACT log `ICE_FAILED`), `turn_fallback_explained` (cần log `TURN_FALLBACK`), `congestion_vs_random_loss` (cần ≥1 đoạn `packet_loss_pct` vượt ngưỡng), `latency_only` (đoạn `rtt_ms` vượt ngưỡng mà participant đó không có đoạn loss), `qoe_impact` (đoạn `mos`/`concealment_pct` vượt ngưỡng), `sfu_isolated_participant` (đi qua SFU và chỉ một phần participant có vi phạm CRITICAL), `healthy_call` (không đoạn nào vượt ngưỡng và không log `ICE_FAILED`/`CALL_FAILED`). Đọc `diagnosis.py` để mô tả đúng logic.
  - `def rule_explain(name: str) -> RuleExplain`: không có → `RuleExplain(title_vi=name, when_vi="(chưa có mô tả cho rule này)")`.
  - `VERDICT_EXPLAIN_VI: dict[Severity, str]`, `MEDIA_PATH_EXPLAIN_VI: dict[MediaPath, str]` (phủ mọi giá trị enum) + `NO_MEDIA_PATH_EXPLAIN_VI: str` (khi `media_path is None`: ICE thất bại, không có media).
  - `def metric_explain_vi(metric: str) -> str`: metric ∈ `THRESHOLDS` (rtt_ms, jitter_ms, packet_loss_pct, mos, concealment_pct); chèn ngưỡng bằng `f"{th.warning:g}"`/`f"{th.critical:g}"` và chiều tốt/xấu từ `th.higher_is_worse`; với `mos` nhắc "MOS là hệ quả của RTT/jitter/loss". Metric lạ → `ValueError`.
- Test phải viết (`tests/test_ui_explain.py`):
  - `set(RULE_EXPLAIN) == {n for n, _ in InferenceEngine().rules}`.
  - `set(MEDIA_PATH_EXPLAIN_VI) == set(MediaPath)`; `set(VERDICT_EXPLAIN_VI) == set(Severity)`.
  - `[t.key for t in find_terms("Fallback TURN vì NAT đối xứng, ICE failed")] == ["TURN", "SYMMETRIC_NAT", "ICE"]`.
  - `find_terms("returned value") == []` (không khớp TURN giữa từ); `find_terms("") == []`; `find_terms("turn turn")` chỉ 1 phần tử.
  - Với mọi metric trong `THRESHOLDS`: `metric_explain_vi(m)` chứa `f"{THRESHOLDS[m].warning:g}"` và `f"{THRESHOLDS[m].critical:g}"`; `metric_explain_vi("cpu")` → `ValueError`.
  - `glossary_markdown()` chứa `name` của mọi term; `glossary_markdown(["SFU"])` chứa "SFU" và không chứa "STUN".
  - `rule_explain("unknown_rule").title_vi == "unknown_rule"`.
  - Mọi `Term.short_vi`, `RuleExplain.when_vi` không rỗng.
- Done khi: `python -m pytest tests/test_ui_explain.py -q` pass.
- Commit: `feat(ui): add vietnamese glossary and rule explanations`

---

### T7: Views — hàm hiển thị thuần (markdown/HTML) cho các tab  [owner: hiepdq] [depends: T1, T2, T4, T6] [parallel-safe: no — đợt 2]
- Files: `src/callops/ui/views.py` (tạo), `tests/test_ui_views.py` (tạo)
- Skill cần gọi: `grounded-diagnosis`, `callops-domain`, `superpowers:test-driven-development`
- Việc cần làm (không import gradio; mọi text từ dữ liệu đi qua `html.escape` khi ra HTML):
  - `def summary_markdown(r: RunResult, beginner: bool) -> str`: scenario_name, nguồn (mô phỏng/upload), `call_id`, verdict, media_path (None → "không có media"), số event/sample/FACT/INFERENCE; nếu có `r.scenario`: description + expected. `beginner` → thêm `VERDICT_EXPLAIN_VI[verdict]` và `MEDIA_PATH_EXPLAIN_VI[...]`/`NO_MEDIA_PATH_EXPLAIN_VI`.
  - `def facts_html(r: RunResult, highlight: Collection[str] = ()) -> str`: `<table class="callops-facts">` cột: ID, t (giây, `r.rel_t(f.ts)` 1 chữ số thập phân), nguồn (log/metric), statement, error_code; `evidence` trong `<details>`. Hàng có id ∈ highlight: `class="hl"` + `<style>` nội tuyến nền nổi bật. Facts rỗng → "Không có FACT".
  - `def inference_choices(r: RunResult) -> list[tuple[str, str]]`: `(f"{i.id} · {hypothesis rút gọn 70 ký tự} (conf {i.confidence:.2f})", i.id)`.
  - `def inference_markdown(r: RunResult, inf_id: str | None, beginner: bool) -> str`: `None`/id lạ → "Chọn một INFERENCE ở danh sách để xem nó dựa trên FACT nào." Ngược lại: tiêu đề "INFERENCE {id} — giả thuyết (không phải dữ kiện)", hypothesis, confidence, reasoning, rule `r.rule_of(id)` + `rule_explain(...).title_vi`, mục "Dựa trên FACT" liệt kê `[Fxx] statement` theo `r.cited_facts(id)`, recommendation nếu có. `beginner` → thêm mục "Thuật ngữ" từ `find_terms(hypothesis + reasoning + recommendation)` (bỏ qua nếu không có term).
  - `def rules_markdown(r: RunResult) -> str`: phần "Rule khớp": `✔ name — title_vi → I01, I02`; phần "Rule không khớp và lý do": `✘ name — Không khớp vì dữ liệu không thỏa: {when_vi}`.
  - `def step_markdown(step: FlowStep | None, beginner: bool) -> str`: None → "Kéo thanh thời gian hoặc bấm Play để xem từng bước."; ngược lại `STEP {step_no} · {STEP_TITLES_VI[step_no]}`, `#{seq} {title}` (t=..s), `actor_from → actor_to`, message gốc, `log_ref`; `beginner` → `explain_vi` + glossary của `find_terms(message + explain_vi)`.
  - `def current_step(steps: Sequence[FlowStep], t: float) -> FlowStep | None`: bước cuối có `step.t <= t` (dùng `flow.steps_until`).
  - `EVENT_COLUMNS: tuple[str, ...] = ("t (s)", "level", "event", "state", "error_code", "message")`; `def events_rows(r: RunResult) -> list[list[Any]]`.
  - `def qos_explain_markdown(beginner: bool) -> str`: `beginner` → `metric_explain_vi` cho 4 metric của chart + concealment; ngược lại 1 dòng ngắn.
- Test phải viết (`tests/test_ui_views.py`; dùng `run_scenario` từ `callops.ui.runner`, cache bằng fixture `scope="module"`):
  - `congestion`: lấy inference có "Nghẽn" → `inference_markdown(r, id, beginner=False)` chứa mọi `[{fid}]` trong `derived_from`, chứa `"congestion_vs_random_loss"`, chứa "giả thuyết"; `beginner=True` có "Thuật ngữ".
  - `facts_html(r, highlight={first_cited})`: đúng 1 hàng `class="hl"` (đếm), và hàng đó chứa id được highlight.
  - Escape: `dataclasses.replace(r, report=r.report.model_copy(update={"facts": [fact có statement "<script>x</script>"] + ...}))` — đơn giản hơn: tạo `RunResult` tối thiểu bằng tay với 1 Fact statement `"<script>x</script>"` và 1 Inference trỏ vào nó → output chứa `"&lt;script&gt;"`, không chứa `"<script>x"`.
  - `p2p_good`: `rules_markdown` chứa `"✔ healthy_call"` và `"✘ ice_failure_root_cause"` kèm `RULE_EXPLAIN["ice_failure_root_cause"].when_vi`.
  - `inference_markdown(r, None, True)` và `(r, "I99", True)` chứa "Chọn một INFERENCE".
  - `ice_failed_no_turn`: `summary_markdown(r, True)` chứa "CRITICAL" và `NO_MEDIA_PATH_EXPLAIN_VI`.
  - `len(events_rows(r)) == len(r.events)`, mỗi hàng dài `len(EVENT_COLUMNS)`.
  - `current_step(steps, -1) is None`; `current_step(steps, 1e9) is steps[-1]`; `step_markdown(None, True)` chứa "Kéo thanh thời gian".
  - `len(inference_choices(r)) == len(r.report.inferences)` và value là id.
- Done khi: `python -m pytest tests/test_ui_views.py -q` pass + toàn bộ `python -m pytest -q` pass.
- Commit: `feat(ui): add pure view helpers for diagnosis, flow and logs tabs`

---

### T8: App Gradio + lệnh `callops ui` + extra `ui`  [owner: hiepdq] [depends: T1–T7] [parallel-safe: no — đợt 3]
- Files: `src/callops/ui/app.py` (tạo), `src/callops/cli.py` (sửa nhỏ), `pyproject.toml` (sửa), `README.md` (thêm mục ngắn), `tests/test_ui_app.py` (tạo), `tests/test_cli_ui.py` (tạo)
- Skill cần gọi: `huggingface-gradio` (API Gradio 6), `callops-domain`, `frontend-design:frontend-design`, `superpowers:test-driven-development`; tra `context7` cho Gradio 6.x nếu không chắc (lưu ý Gradio 6: `theme`/`css`/`head` truyền ở `launch()`, không ở `gr.Blocks(...)`; kiểm tra lại bằng docs).
- Việc cần làm:
  - `pyproject.toml`: `[project.optional-dependencies]` thêm `ui = ["gradio>=4", "plotly>=5", "pyyaml>=6"]` (theo spec; xem Q3). Không đổi dependency khác.
  - `app.py`:
    - Callback là hàm module-level thuần Python (test gọi trực tiếp, không cần server). Mọi callback bắt `UiInputError` → trả thông điệp vào `gr.Markdown` cảnh báo (`⚠️ ...`), giữ nguyên state cũ; không để exception lọt ra.
    - `def render_all(r: RunResult | None, t: float, beginner: bool) -> dict[str, Any]` (hoặc tuple cố định) tạo nội dung mọi output: summary, SVG flow (`render_flow_svg(steps, steps_until(steps, t))`), `step_markdown(current_step(...))`, `qos_figure(r.samples, THRESHOLDS, r.windows, t0=r.t0, cursor_t=t)`, `qos_explain_markdown`, `facts_html`, `inference_choices`, `rules_markdown`, events table, log text. `r is None` → trạng thái rỗng "Chưa có kết quả — chọn kịch bản và bấm Chạy".
    - `def on_run(scenario_text: str, seed: int, beginner: bool) -> ...`: `parse_scenario_text` → `run_scenario(scenario, int(seed))`.
    - `def on_pick_scenario(name: str) -> str`: `scenario_to_yaml(SCENARIOS[name])`.
    - `def on_reanalyze(events_path: str | None, qos_path: str | None, beginner: bool)`: thiếu cả hai → cảnh báo; `load_jsonl`/`load_qos_csv` (file nào có) → `reanalyze(...)`.
    - `def on_load_scenario_file(path: str | None) -> str` (YAML/JSON → text editor).
    - `def on_export(r: RunResult | None) -> tuple[str, str, str]`: ghi vào `tempfile.mkdtemp(prefix="callops-")`: `{call_id}-events.jsonl` (`dump_events_jsonl`), `{call_id}-qos.csv` (`dump_qos_csv`), `{call_id}-report.json` (`report.model_dump_json(indent=2)`); trả 3 path.
    - `def on_select_inference(r, inf_id, beginner)` → `(inference_markdown(...), facts_html(r, highlight=set(inference.derived_from)))`.
    - `def build_app() -> gr.Blocks`: tiêu đề + checkbox "Giải thích cho người mới" (`value=True`); `gr.State` chứa `RunResult | None`; thanh trượt thời gian `gr.Slider(0, duration, step=0.5)` + nút Play/Pause (`gr.Timer(1.0, active=False)`, mỗi tick +1s, dừng ở `duration_s`) đặt **ngay trên `gr.Tabs`** (D5); thay đổi slider → cập nhật flow SVG + step markdown + chart.
      - Tab "Run / Playground": Dropdown `sorted(SCENARIOS)` (mặc định `congestion`), `gr.Code(language="yaml")` chứa scenario YAML (chỉnh được), Number seed (`DEFAULT_SEED`), nút "Chạy mô phỏng", summary markdown, khung cảnh báo.
      - Tab "Call Flow": `gr.HTML` (SVG) + markdown giải thích bước hiện tại.
      - Tab "QoS Timeline": `gr.Plot` + markdown giải thích metric.
      - Tab "Diagnosis": 2 cột — trái `gr.HTML` bảng FACT (highlight), phải `gr.Radio`/`gr.Dropdown` chọn INFERENCE + markdown chi tiết + accordion "Rule khớp / không khớp và lý do" (`rules_markdown`).
      - Tab "Logs / Export": `gr.Dataframe(headers=list(EVENT_COLUMNS))`, `gr.Code` (log_lines, read-only), nút Export → 3 `gr.File`/`gr.DownloadButton`.
      - Tab "Upload / Re-analyze": `gr.File` events `.jsonl`, `gr.File` QoS `.csv`, nút "Phân tích lại"; `gr.File` scenario `.yaml/.yml/.json` → nạp vào editor tab Run.
      - Khi app load: tự chạy kịch bản mặc định (`demo.load`) để mọi tab có nội dung ngay.
    - `def launch(host: str = "127.0.0.1", port: int = 7860, share: bool = False) -> None`: `build_app().launch(server_name=host, server_port=port, share=share, ...)`.
  - `cli.py`: thêm subparser `ui` (`--host` mặc định `127.0.0.1`, `--port` int mặc định `7860`, `--share` store_true); nhánh `if args.cmd == "ui":` đặt **ngay sau nhánh `list`** (trước `setup_logging`/`build_store`, UI luôn dùng in-memory): import lười `from callops.ui.app import launch`; `ImportError` → in ra stderr "Thiếu thư viện UI. Cài: pip install -e .[ui]" và `return 2`; gọi `launch(host=..., port=..., share=...)`, `return 0`. Cập nhật docstring module (`callops ui`). Không đổi hành vi lệnh khác.
  - `README.md`: thêm mục "Demo UI (Gradio)" 5–8 dòng: `pip install -e ".[dev,ui]"`, `callops ui --port 7860`, liệt kê 6 tab.
- Test phải viết:
  - `tests/test_ui_app.py` (`pytest.importorskip("gradio")`, `importorskip("plotly")`, `importorskip("yaml")`):
    - `build_app()` trả `gr.Blocks` không lỗi (không gọi `launch`).
    - `on_run(scenario_to_yaml(SCENARIOS["congestion"]), 42, True)` → state là `RunResult`, không có cảnh báo.
    - `on_run("name: [", 42, True)` → không raise, khung cảnh báo chứa "⚠️", state giữ nguyên (None).
    - `on_reanalyze(None, None, True)` → cảnh báo; round-trip: `on_export(r)` → `on_reanalyze(events_path, qos_path, True)` → `RunResult` cùng verdict.
    - `on_reanalyze` với file CSV thiếu cột → cảnh báo chứa "Thiếu cột".
    - `render_all(None, 0, True)` không lỗi và có chữ "Chưa có kết quả".
    - `on_select_inference` trả HTML có `class="hl"`.
  - `tests/test_cli_ui.py` (`pytest.importorskip("gradio")`): `monkeypatch.setattr("callops.ui.app.launch", fake)` → `main(["ui", "--port", "7861"]) == 0`, fake nhận `port=7861, host="127.0.0.1", share=False`. Test thứ hai: monkeypatch `builtins.__import__` (hoặc `sys.modules["callops.ui.app"] = None`) → `main(["ui"]) == 2`.
- Done khi: toàn bộ `python -m pytest -q` pass; `.venv\Scripts\callops ui --port 7861` khởi động không lỗi (tự tắt sau khi thấy "Running on").
- Commit: `feat(ui): add gradio demo app and callops ui command`

---

### T9: Smoke test thật + chụp màn hình  [owner: hiepdq] [depends: T8] [parallel-safe: no — đợt 4]
- Files: chỉ tạo ảnh trong `docs/screenshots/2026-10-31-gradio/` (xem Q4). **Không sửa source**; lỗi phát hiện → ghi vào báo cáo cho người dùng (fix ở task tiếp theo).
- Skill cần gọi: `browser-automation`, `superpowers:verification-before-completion`
- Việc cần làm:
  1. `python -m pytest -q` pass.
  2. Chạy nền `.venv\Scripts\callops ui --port 7861`, chờ "Running on http://127.0.0.1:7861".
  3. Bằng browser-automation: mở trang, chờ `demo.load` chạy xong kịch bản mặc định; chụp lần lượt: `01-run.png` (tab Run, kịch bản `congestion`), `02-flow.png` (Call Flow, slider ở ~t=12s, thấy band STEP 5 + QOS_ALERT đỏ), `03-qos.png` (vùng sự cố bob t≈10–20s + cursor), `04-diagnosis.png` (chọn INFERENCE "Nghẽn..." → FACT được highlight + accordion rule mở), `05-logs.png`, `06-upload-error.png` (upload 1 file CSV thiếu cột → cảnh báo hiển thị, app không crash), `07-ice-failed-flow.png` (chạy `ice_failed_no_turn`, flow có ICE_FAILED đỏ, chart báo không có dữ liệu QoS), `08-group-sfu-diagnosis.png`.
  4. Kiểm: console không có lỗi JS, không có request lỗi 5xx; tự xem từng ảnh — SVG hiển thị (không bị Gradio lọc mất `<style>`), animation bước `current` có tác dụng, chữ tiếng Việt không lỗi font, chart có 4 hàng.
  5. Bấm Play vài giây → slider tăng, flow + chart cùng cập nhật.
  6. Tắt server.
- Done khi: đủ 8 ảnh, không lỗi console; báo cáo liệt kê ảnh + vấn đề hiển thị (nếu có).
- Commit: `docs(ui): add gradio demo screenshots` (chỉ khi người dùng chọn lưu ảnh trong repo).
