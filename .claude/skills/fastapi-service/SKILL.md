---
name: fastapi-service
description: Conventions for exposing callops simulation, anomaly detection and diagnosis through an async FastAPI REST service - project layout, Pydantic v2 request/response models reusing callops.models, dependency injection of TelemetryStore and settings, running blocking work off the event loop, error mapping, and testing with httpx AsyncClient. Use when writing code under src/callops/api/.
---

# FastAPI service cho callops

## Layout

```
src/callops/api/
  app.py         # create_app(settings) -> FastAPI, lifespan mở/đóng store
  deps.py        # get_settings, get_store (Depends)
  schemas.py     # request/response riêng của API (tái dùng models.py khi được)
  routers/
    calls.py     # GET /calls/{call_id}, GET /calls/{call_id}/qos
    diagnosis.py # POST /calls/{call_id}/diagnosis -> DiagnosisReport
    anomaly.py   # GET /calls/{call_id}/anomalies
```

## Quy ước

- App factory `create_app()` (không tạo app ở import time) → test tạo app với store in-memory.
- `lifespan` khởi tạo `build_store(...)` từ `config.py`, gắn vào `app.state`; `deps.get_store` đọc từ đó.
- `response_model` luôn khai báo; trả trực tiếp `DiagnosisReport`, `QoSSample` (Pydantic v2) — không dict tự do.
- Route `async def`. `DockerStore` hiện dùng client **đồng bộ** (redis, httpx.Client) → gọi qua `await run_in_threadpool(...)` hoặc chuyển sang `httpx.AsyncClient`/`redis.asyncio`; không chặn event loop.
- Lỗi: không tìm thấy call → `HTTPException(404)`; lỗi validate grounding → 422 kèm danh sách lỗi; backend down → 503.
- Request lớn (diagnosis bằng LLM) → cân nhắc trả `202` + job id, poll kết quả.

## Test

```python
@pytest.fixture
async def client():
    app = create_app(Settings(backend="memory"))
    async with LifespanManager(app), httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
```

- Dùng `pytest-asyncio` (hoặc `anyio`), backend memory, seed cố định.
- Có thể override dependency: `app.dependency_overrides[get_store] = lambda: fake_store`.

## Dependency (thêm khi bắt đầu)

`fastapi`, `uvicorn[standard]` vào optional group `api`; dev thêm `pytest-asyncio`, `asgi-lifespan`.
Chạy: `uvicorn callops.api.app:create_app --factory --reload`.
