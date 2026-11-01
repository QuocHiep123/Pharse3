---
name: calldiag-add-scenario
description: Thêm kịch bản telemetry mới cho CallDiag (S7, S8, ...) - module scenarios/sN_*.py dùng ScenarioBuilder / Profile / Plateau, đăng ký vào REGISTRY, viết ExpectedOutcome cho eval, sinh lại data/scenarios và sửa các test đếm số kịch bản. Dùng khi cần mô phỏng một loại sự cố mới hoặc một biến thể của kịch bản có sẵn.
---

# Thêm kịch bản

Đọc trước: mục 6–7 trong `docs/MVP_PLAN.md`. Pipeline **không được** biết kịch bản nào đang chạy: không thêm nhánh theo scenario ID vào `pipeline/` hay `config.py`.

## Các bước

1. **Dữ liệu dùng chung** (`calldiag/scenarios/data.py`): thêm tiêu đề vào `SCENARIO_TITLES` và nới `SCENARIO_SEEDS = {f"S{i}": 1000 + i for i in range(7)}` cho đủ số kịch bản. `SCENARIO_CALL_IDS` tự sinh từ seed.
2. **Module kịch bản** `calldiag/scenarios/sN_<tên>.py` có hàm `build() -> CallTelemetry`:
   - Cuộc gọi có media: `build_media_scenario(new_builder("SN"), mode="p2p" | "relay", qos=qos_profiles(plateaus=...), turn_cpu=Profile(...), logs=..., missing_sources=...)`.
   - Fail sớm: ghép `add_setup`, `add_offer_answer_ok` / `add_offer_answer_timeout`, `add_ice(b, "fail")`, ... từ `scenarios/common.py` (xem `s3_ice_failure.py`, `s5_signaling_timeout.py`).
   - Plateau là `(t_start, t_end, mean, std[, ramp_in, ramp_out])`; log là `(offset, component, level, category, call_scoped, message)`.
   - Metric thiếu: `Profile(0.0, 0.0, missing=True)` (giá trị thành `None`) và ghi lý do vào `missing_sources` (xem `s6_missing_turn_metrics.py`).
   - Tham số riêng của kịch bản để trong chính module đó, không đưa vào `config.py`.
3. **Đăng ký** trong `calldiag/scenarios/__init__.py`: import module và thêm `("SN", sN_x.build, "mô tả")` vào `REGISTRY`.
4. **Kỳ vọng** trong `calldiag/scenarios/expected.py`: thêm `ExpectedOutcome` (trạng thái 5 phase, có incident, khoảng incident theo giây từ đầu cuộc gọi hoặc `None`, rule chính, confidence, severity, `required_*`, `forbidden_inferences`, `required_missing_metrics`).
5. **Sinh lại dữ liệu**: `python -m calldiag generate --scenario all` (cập nhật `data/scenarios/`).
6. **Test đang đếm cứng 7 kịch bản**, cần cập nhật: `tests/test_cli.py` (số file json/md, số dòng "validation: passed"), `tests/test_generator.py` (số dòng output, số file, thông báo `S0, S1, …` khi ID sai, và kịch bản S7 không hợp lệ). Thêm case mới vào các test parametrize theo `via_turn` nếu có.
7. **Kiểm tra**: `pytest -q` và `python -m calldiag eval` (giờ phải `N/N PASS`). Mở UI xem kịch bản mới hiển thị đúng.
8. Cập nhật bảng kịch bản trong `README.md` và `docs/MVP_PLAN.md`.

## Gợi ý thiết kế kịch bản

Mỗi kịch bản nên kiểm một hành vi của bộ suy luận, không chỉ thêm dữ liệu: ví dụ một nguồn gây nhiễu không nằm trên path (như S2), một nguồn bị thiếu (như S6), hoặc counter-evidence làm giảm confidence (client CPU cao). Viết `forbidden_inferences` cho kết luận sai dễ mắc nhất.
