---
name: timeseries-anomaly-xai
description: Time-series preprocessing, multivariate anomaly detection and explainability for callops QoS metrics - pandas resampling and rolling features (mean, variance, trend slope), rolling Z-score, EWMA control charts, Pearson/Spearman correlation between network latency and TURN/SFU resource usage, and SHAP TreeExplainer attribution of call-quality degradation. Use when writing code under src/callops/anomaly/ or src/callops/pipeline/, or analysing QoSSample data.
---

# Time-series anomaly detection + XAI

Input chuẩn: list `QoSSample` (`models.py`), 1 mẫu/giây/participant. Ngưỡng tĩnh nằm ở `THRESHOLDS` (`qos.py`) — anomaly detector **bổ sung** cho ngưỡng tĩnh, không thay thế.

## Tiền xử lý

```python
df = pd.DataFrame([s.model_dump() for s in samples])
df = df.set_index("ts").sort_index()
per_p = (df.groupby("participant_id")[METRICS]
           .resample("1s").mean()          # điền lỗ hổng thời gian
           .groupby(level=0).ffill(limit=3))
roll = per_p.groupby(level=0).rolling("10s")
feat_mean, feat_var = roll.mean(), roll.var()
# trend slope: hệ số góc hồi quy tuyến tính trong cửa sổ
slope = roll.apply(lambda w: np.polyfit(np.arange(len(w)), w, 1)[0] if len(w) > 2 else 0.0, raw=True)
```

- Luôn tính **theo từng participant** (groupby) trước khi gộp — SFU call có thể chỉ 1 người xấu.
- Index thời gian UTC, tz-aware.

## Phát hiện bất thường

| Kỹ thuật | Công thức / cách dùng | Ghi chú |
|---|---|---|
| Rolling Z-score | `z = (x - rolling_mean) / rolling_std`, cờ khi `|z| > 3` | Dùng cửa sổ **quá khứ** (`shift(1)`) để tránh leak |
| EWMA | `ewm(span=10).mean()` + control limit `±L·σ_ewma` | Nhạy với drift chậm |
| Đa biến | Gộp cờ: ≥ 2 metric bất thường cùng cửa sổ → anomaly; hoặc IsolationForest trên vector feature | Ghi rõ metric nào góp phần |
| Correlation | `df[["rtt_ms","turn_cpu","turn_bw"]].corr(method="spearman")` trên cửa sổ sự cố | Spearman khi phân phối lệch / có outlier |

Output detector phải chuyển được thành **FACT** (source="metric", có `ts`, `evidence` = giá trị + z-score/ngưỡng) để agent của Hiệp dùng — xem `grounded-diagnosis`.

## XAI với SHAP

```python
model = GradientBoostingClassifier().fit(X_train, y_degraded)   # hoặc XGBoost/LightGBM
explainer = shap.TreeExplainer(model)
sv = explainer(X_window)               # shap.Explanation
contrib = pd.Series(sv.values[i], index=X.columns).sort_values(key=abs, ascending=False)
```

- Label `y_degraded` lấy từ MOS ≤ ngưỡng warning hoặc từ kịch bản lỗi trong `scenarios.py`.
- Báo cáo top-k feature + dấu (+ tăng rủi ro / − giảm) cho từng sự cố; đó là **INFERENCE**, phải cite FACT metric tương ứng.
- Với phân loại nhị phân, kiểm tra shape `sv.values` (một số model trả 2 lớp).
- Vẽ: `shap.plots.waterfall`, `beeswarm` — dùng skill `dataviz` cho biểu đồ metric.

## Quy tắc

- Hàm thuần (`DataFrame -> DataFrame`), không I/O bên trong → dễ test.
- Test với dữ liệu tổng hợp có anomaly cài sẵn (biết trước vị trí) + seed cố định.
- Dependency (thêm khi bắt đầu): `pandas`, `numpy`, `scikit-learn`, `statsmodels`, `shap` vào optional group `data`.
