"""CLI:  callops list | callops check-env | callops run <scenario> | callops run-all"""

from __future__ import annotations

import argparse
import logging
import sys
import textwrap
from datetime import datetime
from pathlib import Path

from callops.config import Settings
from callops.diagnosis import DiagnosisService
from callops.logging_setup import setup_logging
from callops.models import DiagnosisReport, Severity
from callops.scenarios import SCENARIOS
from callops.simulator import CallSimulator
from callops.storage import TelemetryStore, build_store

log = logging.getLogger("callops.cli")

_SEV_COLOR = {Severity.OK: "\033[32m", Severity.WARNING: "\033[33m", Severity.CRITICAL: "\033[31m"}


def print_report(r: DiagnosisReport) -> None:
    w = 100
    c = _SEV_COLOR[r.verdict]
    print("\n" + "═" * w)
    print(f" AIOps DIAGNOSIS  {r.call_id}   verdict={c}{r.verdict.value}\033[0m   media_path={r.media_path and r.media_path.value}")
    print("═" * w)
    print(" FACT (dữ kiện trích trực tiếp từ log/metric, có timestamp + evidence):")
    for f in r.facts:
        print(f"  {f.id} {f.ts:%H:%M:%S.%f}"[:-3] + f" [{f.source:<6}] {f.statement}")
        if f.error_code:
            print(f"      code={f.error_code}")
        print(textwrap.indent(textwrap.shorten(f"evidence: {f.evidence}", 300), "      \033[90m") + "\033[0m")
    print("─" * w)
    print(" INFERENCE (giả thuyết suy ra, bắt buộc trỏ về FACT):")
    for i in r.inferences:
        print(f"  {i.id} (conf={i.confidence:.2f}) {i.hypothesis}")
        print(textwrap.indent(textwrap.fill(f"vì: {i.reasoning}", w - 8), "      "))
        print(f"      dựa trên FACT: {', '.join(i.derived_from)}")
        if i.recommendation:
            print(f"      → khuyến nghị: {i.recommendation}")
    print("═" * w + "\n")


def run_one(name: str, store: TelemetryStore, settings: Settings, out_dir: Path) -> DiagnosisReport:
    sim = CallSimulator(SCENARIOS[name], store, seed=settings.seed)
    result = sim.run()
    log.info("Kết thúc mô phỏng: state=%s path=%s", result.final_state.value,
             result.media_path.value if result.media_path else None)
    log.info("━" * 18 + " [STEP 7] AIOps DIAGNOSIS (FACT -> INFERENCE) " + "━" * 18)
    report = DiagnosisService(store).diagnose(result.call_id, name)
    print_report(report)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{result.call_id}.json"
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    log.info("Report JSON: %s", path)
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="callops", description=__doc__)
    ap.add_argument("--backend", choices=["auto", "memory"], help="ghi đè CALLOPS_BACKEND")
    ap.add_argument("--log-level", help="DEBUG (chi tiết từng mẫu metric/ICE check) | INFO")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="liệt kê kịch bản")
    sub.add_parser("check-env", help="kiểm tra kết nối Redis/OpenSearch")
    p_run = sub.add_parser("run", help="chạy 1 kịch bản")
    p_run.add_argument("scenario", choices=sorted(SCENARIOS))
    sub.add_parser("run-all", help="chạy tất cả kịch bản")
    args = ap.parse_args(argv)

    settings = Settings()
    if args.backend:
        settings.backend = args.backend
    if args.log_level:
        settings.log_level = args.log_level

    if args.cmd == "list":
        sys.stdout.reconfigure(encoding="utf-8")
        for s in SCENARIOS.values():
            print(f"{s.name:<20} {s.description}\n{'':<20} kỳ vọng: {s.expected}")
        return 0

    run_id = datetime.now().strftime("run-%Y%m%d-%H%M%S")
    log_file = setup_logging(settings.log_level, settings.log_dir, run_id)
    log.info("Log JSONL: %s", log_file)
    store = build_store(settings.backend, settings.redis_url, settings.opensearch_url)

    if args.cmd == "check-env":
        return 0 if store.name != "memory" or settings.backend == "memory" else 1

    names = [args.scenario] if args.cmd == "run" else list(SCENARIOS)
    reports = [run_one(n, store, settings, Path("reports")) for n in names]
    if len(reports) > 1:
        print(f"{'scenario':<20} {'path':<12} {'verdict':<9} top inference")
        for r in reports:
            top = r.inferences[0].hypothesis if r.inferences else "-"
            print(f"{r.scenario:<20} {(r.media_path.value if r.media_path else 'NONE'):<12} {r.verdict.value:<9} {top}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
