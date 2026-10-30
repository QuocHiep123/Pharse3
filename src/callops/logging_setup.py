"""Logging 2 đầu ra:

- Console: dễ đọc cho người, mỗi dòng có [STEP] / component để theo dõi luồng.
- File JSONL (logs/<run_id>.jsonl): mỗi dòng là 1 JSON có timestamp + extra fields.
  Đây chính là "log gốc" mà engine AIOps trích FACT ra (giống log thật ở production).
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_RESERVED = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}

_COLORS = {
    "DEBUG": "\033[90m",
    "INFO": "\033[36m",
    "WARNING": "\033[33m",
    "ERROR": "\033[31m",
    "CRITICAL": "\033[41m",
}
_RESET = "\033[0m"


def _extras(record: logging.LogRecord) -> dict[str, Any]:
    return {k: v for k, v in record.__dict__.items() if k not in _RESERVED}


class ConsoleFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created).strftime("%H:%M:%S.%f")[:-3]
        color = _COLORS.get(record.levelname, "")
        comp = record.name.removeprefix("callops.")
        line = f"{ts} {color}{record.levelname:<7}{_RESET} {comp:<10} | {record.getMessage()}"
        extras = _extras(record)
        if extras:
            kv = " ".join(f"{k}={v}" for k, v in extras.items())
            line += f"\n{'':>31}\033[90m↳ {kv}{_RESET}"
        return line


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "@timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            **_extras(record),
        }
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(level: str, log_dir: str, run_id: str) -> Path:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Windows console + tiếng Việt
    root = logging.getLogger("callops")
    root.setLevel(level.upper())
    root.handlers.clear()
    root.propagate = False

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(ConsoleFormatter())
    root.addHandler(console)

    path = Path(log_dir)
    path.mkdir(parents=True, exist_ok=True)
    log_file = path / f"{run_id}.jsonl"
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(JsonFormatter())
    root.addHandler(fh)
    return log_file
