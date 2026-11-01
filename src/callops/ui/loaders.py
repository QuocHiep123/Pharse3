"""Đọc/ghi JSONL event, CSV QoS và scenario YAML/JSON; mọi lỗi đầu vào -> UiInputError (tiếng Việt)."""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable
from pathlib import Path

from pydantic import ValidationError

from callops.models import CallEvent, QoSSample
from callops.scenarios import Scenario
from callops.ui.contracts import UiInputError

__all__ = [
    "QOS_CSV_COLUMNS",
    "load_jsonl",
    "load_qos_csv",
    "parse_scenario_text",
    "load_scenario",
    "scenario_to_yaml",
    "dump_events_jsonl",
    "dump_qos_csv",
]

QOS_CSV_COLUMNS: tuple[str, ...] = tuple(QoSSample.model_fields)

_YAML_MISSING = "Cần cài extra ui: pip install -e .[ui]"


def _locs(exc: ValidationError) -> str:
    """Gom tên trường lỗi (loc) không trùng lặp, giữ thứ tự."""
    seen: list[str] = []
    for err in exc.errors():
        name = ".".join(str(p) for p in err["loc"]) or "?"
        if name not in seen:
            seen.append(name)
    return ", ".join(seen)


def _read_text(p: Path) -> str:
    if not p.is_file():
        raise UiInputError(f"Không tìm thấy file: {p}")
    try:
        return p.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        raise UiInputError(f"Không đọc được file {p.name}: {exc}") from exc


def load_jsonl(path: str | Path) -> list[CallEvent]:
    p = Path(path)
    text = _read_text(p)
    events: list[CallEvent] = []
    for n, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise UiInputError(f"{p.name} - Dòng {n}: không phải JSON hợp lệ ({exc.msg})") from exc
        if isinstance(obj, dict) and "@timestamp" in obj and "logger" in obj:
            raise UiInputError(
                f"{p.name} - Dòng {n}: đây là log JSONL của logging (logs/run-*.jsonl), "
                "không phải event export; hãy dùng file export ở tab Logs/Export."
            )
        try:
            events.append(CallEvent.model_validate(obj))
        except ValidationError as exc:
            raise UiInputError(f"{p.name} - Dòng {n}: thiếu/sai trường: {_locs(exc)}") from exc
    if not events:
        raise UiInputError(f"File rỗng, không có event nào: {p.name}")
    return events


def load_qos_csv(path: str | Path) -> list[QoSSample]:
    p = Path(path)
    text = _read_text(p)
    reader = csv.DictReader(text.splitlines())
    missing = [c for c in QOS_CSV_COLUMNS if c not in (reader.fieldnames or [])]
    if missing:
        raise UiInputError(f"{p.name} - Thiếu cột: {', '.join(missing)}")
    samples: list[QoSSample] = []
    for n, row in enumerate(reader, start=2):  # dòng 1 là header
        try:
            samples.append(QoSSample.model_validate({c: row[c] for c in QOS_CSV_COLUMNS}))
        except (ValidationError, KeyError) as exc:
            detail = _locs(exc) if isinstance(exc, ValidationError) else f"thiếu giá trị {exc}"
            raise UiInputError(f"{p.name} - Dòng {n}: thiếu/sai trường: {detail}") from exc
    if not samples:
        raise UiInputError(f"File rỗng, không có dòng dữ liệu nào: {p.name}")
    return samples


def parse_scenario_text(text: str, *, source: str = "<text>") -> Scenario:
    if not text or not text.strip():
        raise UiInputError(f"{source}: nội dung scenario rỗng")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        try:
            import yaml
        except ImportError as exc:
            raise UiInputError(_YAML_MISSING) from exc
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise UiInputError(f"{source}: không phải JSON/YAML hợp lệ ({exc})") from exc
    if not isinstance(data, dict):
        raise UiInputError(f"{source}: scenario phải là một object (name, participants, ...)")
    try:
        return Scenario.model_validate(data)
    except ValidationError as exc:
        detail = "; ".join(
            f"{'.'.join(str(p) for p in e['loc']) or '?'}: {e['msg']}" for e in exc.errors()
        )
        raise UiInputError(f"{source}: scenario không hợp lệ - {detail}") from exc


def load_scenario(path: str | Path) -> Scenario:
    p = Path(path)
    if p.suffix.lower() not in (".yaml", ".yml", ".json"):
        raise UiInputError("Chỉ hỗ trợ .yaml, .yml, .json")
    return parse_scenario_text(_read_text(p), source=p.name)


def scenario_to_yaml(scenario: Scenario) -> str:
    try:
        import yaml
    except ImportError as exc:
        raise UiInputError(_YAML_MISSING) from exc
    return yaml.safe_dump(scenario.model_dump(mode="json"), allow_unicode=True, sort_keys=False)


def dump_events_jsonl(events: Iterable[CallEvent], path: str | Path) -> Path:
    p = Path(path)
    lines = (json.dumps(ev.model_dump(mode="json"), ensure_ascii=False) for ev in events)
    p.write_text("".join(f"{ln}\n" for ln in lines), encoding="utf-8")
    return p


def dump_qos_csv(samples: Iterable[QoSSample], path: str | Path) -> Path:
    p = Path(path)
    with p.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(QOS_CSV_COLUMNS))
        writer.writeheader()
        for s in samples:
            writer.writerow(s.model_dump(mode="json"))
    return p
