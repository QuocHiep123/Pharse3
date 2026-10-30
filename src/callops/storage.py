"""Lưu trữ telemetry.

- Redis       : trạng thái "live" của cuộc gọi (HASH call:<id>) - giống session store thật.
- OpenSearch  : index log sự kiện + metric QoS để AIOps truy vấn lại (callops-events, callops-qos).
- InMemory    : fallback khi không chạy Docker (cùng interface, dùng cho test).
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any

import httpx

log = logging.getLogger("callops.storage")

EVENTS_INDEX = "callops-events"
QOS_INDEX = "callops-qos"


class TelemetryStore(ABC):
    name: str = "abstract"

    @abstractmethod
    def set_call_state(self, call_id: str, fields: dict[str, str]) -> None: ...

    @abstractmethod
    def get_call_state(self, call_id: str) -> dict[str, str]: ...

    @abstractmethod
    def index(self, index: str, doc: dict[str, Any]) -> None: ...

    @abstractmethod
    def search(self, index: str, call_id: str) -> list[dict[str, Any]]: ...

    def flush(self) -> None:
        """Đảm bảo dữ liệu đã ghi có thể đọc lại (OpenSearch cần refresh)."""


class InMemoryStore(TelemetryStore):
    name = "memory"

    def __init__(self) -> None:
        self._state: dict[str, dict[str, str]] = {}
        self._docs: dict[str, list[dict[str, Any]]] = {}

    def set_call_state(self, call_id: str, fields: dict[str, str]) -> None:
        self._state.setdefault(call_id, {}).update(fields)

    def get_call_state(self, call_id: str) -> dict[str, str]:
        return dict(self._state.get(call_id, {}))

    def index(self, index: str, doc: dict[str, Any]) -> None:
        self._docs.setdefault(index, []).append(doc)

    def search(self, index: str, call_id: str) -> list[dict[str, Any]]:
        docs = [d for d in self._docs.get(index, []) if d.get("call_id") == call_id]
        return sorted(docs, key=lambda d: d["ts"])


class DockerStore(TelemetryStore):
    """Redis + OpenSearch thật (chạy bằng docker compose)."""

    name = "redis+opensearch"

    def __init__(self, redis_url: str, opensearch_url: str) -> None:
        import redis

        self._redis = redis.Redis.from_url(redis_url, decode_responses=True, socket_timeout=2)
        self._redis.ping()
        self._http = httpx.Client(base_url=opensearch_url, timeout=10)
        self._http.get("/").raise_for_status()
        self._bulk: list[str] = []
        for idx in (EVENTS_INDEX, QOS_INDEX):
            if self._http.head(f"/{idx}").status_code == 404:
                self._http.put(
                    f"/{idx}", json={"mappings": {"properties": {"ts": {"type": "date"}, "call_id": {"type": "keyword"}}}}
                ).raise_for_status()
                log.info("Tạo index OpenSearch %s", idx)

    def set_call_state(self, call_id: str, fields: dict[str, str]) -> None:
        key = f"call:{call_id}"
        self._redis.hset(key, mapping=fields)
        self._redis.expire(key, 3600)

    def get_call_state(self, call_id: str) -> dict[str, str]:
        return self._redis.hgetall(f"call:{call_id}")

    def index(self, index: str, doc: dict[str, Any]) -> None:
        # gom bulk cho nhanh, flush() trước khi đọc
        self._bulk.append(json.dumps({"index": {"_index": index}}))
        self._bulk.append(json.dumps(doc, default=str, ensure_ascii=False))
        if len(self._bulk) >= 400:
            self.flush()

    def flush(self) -> None:
        if self._bulk:
            body = "\n".join(self._bulk) + "\n"
            r = self._http.post("/_bulk", content=body.encode(), headers={"Content-Type": "application/x-ndjson"})
            r.raise_for_status()
            if r.json().get("errors"):
                raise RuntimeError(f"OpenSearch bulk lỗi: {r.text[:500]}")
            log.debug("Bulk index %d docs vào OpenSearch", len(self._bulk) // 2)
            self._bulk.clear()
        self._http.post(f"/{EVENTS_INDEX},{QOS_INDEX}/_refresh").raise_for_status()

    def search(self, index: str, call_id: str) -> list[dict[str, Any]]:
        query = {"size": 10000, "query": {"term": {"call_id": call_id}}, "sort": [{"ts": "asc"}]}
        r = self._http.post(f"/{index}/_search", json=query)
        r.raise_for_status()
        return [h["_source"] for h in r.json()["hits"]["hits"]]


def build_store(backend: str, redis_url: str, opensearch_url: str) -> TelemetryStore:
    if backend == "memory":
        log.info("Backend = in-memory (theo cấu hình)")
        return InMemoryStore()
    try:
        store = DockerStore(redis_url, opensearch_url)
        log.info("Backend = Redis (%s) + OpenSearch (%s)", redis_url, opensearch_url)
        return store
    except Exception as exc:  # noqa: BLE001 - fallback có chủ đích
        log.warning("Không kết nối được Redis/OpenSearch (%s) -> fallback in-memory. "
                    "Chạy `docker compose up -d` để dùng backend thật.", type(exc).__name__)
        return InMemoryStore()
