"""Generate telemetry and run local call diagnosis."""

import argparse
from pathlib import Path

from calldiag import config
from calldiag import eval as evaluation
from calldiag.envfile import load_env_file
from calldiag.io import load_bundle, save_bundle, save_pipeline_outputs
from calldiag.pipeline.run import run_pipeline
from calldiag.scenarios import REGISTRY, get_scenario


def main(argv: list[str] | None = None) -> int:
    load_env_file()
    parser = argparse.ArgumentParser(prog="calldiag")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="Liệt kê các kịch bản giả lập")
    generate = commands.add_parser("generate", help="Sinh telemetry giả lập thành JSON")
    generate.add_argument("--scenario", choices=[*REGISTRY, "all"], default="all")
    generate.add_argument("--out", type=Path, default=Path(config.DEFAULT_SCENARIO_DIR))
    run = commands.add_parser("run", help="Chẩn đoán cuộc gọi, xuất report và trace")
    source = run.add_mutually_exclusive_group(required=True)
    source.add_argument("--scenario", choices=[*REGISTRY, "all"])
    source.add_argument("--input", type=Path)
    run.add_argument("--out", type=Path, default=Path(config.DEFAULT_OUTPUT_DIR))
    run.add_argument("--llm", action="store_true")
    run.add_argument("--strict", action="store_true")
    bench = commands.add_parser("eval", help="So kết quả 7 kịch bản với ExpectedOutcome, ghi bảng PASS/FAIL")
    bench.add_argument("--out", type=Path, default=Path(config.DEFAULT_OUTPUT_DIR))
    args = parser.parse_args(argv)
    if args.command == "eval":
        evals = evaluation.run_eval()
        path = args.out / "eval.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(evaluation.render_eval_markdown(evals), encoding="utf-8")
        print(evaluation.render_eval_table(evals))
        print(f"→ {path}")
        return int(not all(e.passed for e in evals))
    if args.command == "list":
        for scenario in REGISTRY.values():
            print(f"{scenario.id}  {scenario.title:<36} {scenario.description}")
        return 0
    if args.command == "run":
        failed = False
        try:
            bundles = (load_bundle(args.input),) if args.input is not None else (
                scenario.build() for scenario in (REGISTRY.values() if args.scenario == "all" else (get_scenario(args.scenario),))
            )
            for bundle in bundles:
                result = run_pipeline(bundle, use_llm=args.llm)
                result.report.scenario_id = bundle.meta.scenario_id
                paths = save_pipeline_outputs(result, args.out)
                report = result.report
                confidence = report.summary.confidence.value if report.summary.confidence is not None else "unknown"
                passed = report.validation is not None and report.validation.passed
                failed |= not passed
                print(f"[{report.scenario_id}] {report.scope.call_id}")
                print(f"  {report.summary.headline}")
                print(f"  severity={report.summary.severity.value}  confidence={confidence}  facts={len(report.facts)}  inferences={len(report.inferences)}  hypotheses={len(report.hypotheses)}  rejected={len(report.rejected)}")
                print(f"  validation: {'passed' if passed else 'failed'}")
                for issue in report.validation.issues if report.validation else ():
                    print(f"  {issue.level} {issue.code}: {issue.message}")
                print("  → " + ", ".join(str(path) for path in paths))
        except (OSError, ValueError) as exc:
            parser.error(str(exc))
        return int(args.strict and failed)
    scenarios = REGISTRY.values() if args.scenario == "all" else (get_scenario(args.scenario),)
    for scenario in scenarios:
        path = args.out / f"{scenario.id}.json"
        save_bundle(scenario.build(), path)
        print(path)
    return 0
