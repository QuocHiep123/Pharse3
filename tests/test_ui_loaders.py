"""Test loaders của callops.ui: JSONL / CSV / scenario YAML-JSON."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from callops.models import CallEvent, QoSSample
from callops.scenarios import SCENARIOS, Scenario
from callops.simulator import CallSimulator
from callops.storage import EVENTS_INDEX, QOS_INDEX, InMemoryStore
from callops.ui.contracts import UiInputError
from callops.ui.loaders import (
    QOS_CSV_COLUMNS,
    dump_events_jsonl,
    dump_qos_csv,
    load_jsonl,
    load_qos_csv,
    load_scenario,
    parse_scenario_text,
    scenario_to_yaml,
)

needs_yaml = pytest.mark.skipif(importlib.util.find_spec("yaml") is None, reason="cần PyYAML")


@pytest.fixture(scope="module")
def data() -> tuple[list[CallEvent], list[QoSSample]]:
    store = InMemoryStore()
    result = CallSimulator(SCENARIOS["congestion"], store, seed=42).run()
    cid = result.call_id
    events = [CallEvent.model_validate(d) for d in store.search(EVENTS_INDEX, cid)]
    samples = [QoSSample.model_validate(d) for d in store.search(QOS_INDEX, cid)]
    return events, samples


def test_roundtrip_events(tmp_path: Path, data) -> None:
    events, _ = data
    out = dump_events_jsonl(events, tmp_path / "e.jsonl")
    assert isinstance(out, Path)
    loaded = load_jsonl(out)
    assert [e.model_dump() for e in loaded] == [e.model_dump() for e in events]


def test_roundtrip_qos(tmp_path: Path, data) -> None:
    _, samples = data
    out = dump_qos_csv(samples, tmp_path / "q.csv")
    loaded = load_qos_csv(out)
    assert [s.model_dump() for s in loaded] == [s.model_dump() for s in samples]


def test_qos_columns() -> None:
    assert QOS_CSV_COLUMNS == tuple(QoSSample.model_fields)


def test_load_jsonl_errors(tmp_path: Path) -> None:
    with pytest.raises(UiInputError, match="Không tìm thấy"):
        load_jsonl(tmp_path / "nope.jsonl")

    blank = tmp_path / "blank.jsonl"
    blank.write_text("\n  \n\n", encoding="utf-8")
    with pytest.raises(UiInputError, match="rỗng"):
        load_jsonl(blank)

    bad = tmp_path / "bad.jsonl"
    bad.write_text("{not json\n", encoding="utf-8")
    with pytest.raises(UiInputError, match="Dòng 1"):
        load_jsonl(bad)

    miss = tmp_path / "miss.jsonl"
    miss.write_text(
        json.dumps({"ts": "2026-01-01T00:00:00", "event": "INVITE", "state": "SETUP", "message": "x"}),
        encoding="utf-8",
    )
    with pytest.raises(UiInputError, match="call_id"):
        load_jsonl(miss)

    logf = tmp_path / "log.jsonl"
    logf.write_text(
        json.dumps({"@timestamp": "2026-01-01T00:00:00", "logger": "callops.call", "message": "x"}),
        encoding="utf-8",
    )
    with pytest.raises(UiInputError, match="logs/run"):
        load_jsonl(logf)


def test_load_qos_csv_errors_and_bom(tmp_path: Path, data) -> None:
    _, samples = data
    cols = [c for c in QOS_CSV_COLUMNS if c not in ("mos", "rtt_ms")]
    f = tmp_path / "missing.csv"
    f.write_text(",".join(cols) + "\n", encoding="utf-8")
    with pytest.raises(UiInputError) as ei:
        load_qos_csv(f)
    assert "rtt_ms" in str(ei.value) and "mos" in str(ei.value)

    good = dump_qos_csv(samples[:1], tmp_path / "g.csv")
    text = good.read_text(encoding="utf-8").replace(
        str(samples[0].rtt_ms), "abc", 1
    )
    bad = tmp_path / "bad.csv"
    bad.write_text(text, encoding="utf-8")
    with pytest.raises(UiInputError, match="Dòng 2"):
        load_qos_csv(bad)

    bom = tmp_path / "bom.csv"
    bom.write_bytes(b"\xef\xbb\xbf" + good.read_bytes())
    assert len(load_qos_csv(bom)) == 1

    empty = tmp_path / "empty.csv"
    empty.write_text(",".join(QOS_CSV_COLUMNS) + "\n", encoding="utf-8")
    with pytest.raises(UiInputError, match="rỗng"):
        load_qos_csv(empty)


@needs_yaml
def test_scenario_yaml_roundtrip_and_files(tmp_path: Path) -> None:
    sc = SCENARIOS["group_sfu"]
    text = scenario_to_yaml(sc)
    assert parse_scenario_text(text).model_dump() == sc.model_dump()

    y = tmp_path / "s.YAML"
    y.write_text(text, encoding="utf-8")
    assert isinstance(load_scenario(y), Scenario)
    j = tmp_path / "s.json"
    j.write_text(json.dumps(sc.model_dump(mode="json")), encoding="utf-8")
    assert load_scenario(j).model_dump() == sc.model_dump()


def test_scenario_json_text() -> None:
    sc = SCENARIOS["p2p_good"]
    got = parse_scenario_text(json.dumps(sc.model_dump(mode="json")))
    assert got.model_dump() == sc.model_dump()


@needs_yaml
def test_scenario_bad_inputs() -> None:
    for bad in ("name: x\nparticipants: []", "- a\n- b", "", "   "):
        with pytest.raises(UiInputError):
            parse_scenario_text(bad)


def test_load_scenario_bad_ext(tmp_path: Path) -> None:
    with pytest.raises(UiInputError, match=r"\.yaml"):
        load_scenario("x.txt")
