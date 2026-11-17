"""Command-line entry point: reproduce an analysis without the UI.

uv run vcu-impact analyze                         # provided files, recording if available
uv run vcu-impact analyze --revised my_spec.docx --mode live
uv run vcu-impact analyze --json out.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from vcu_impact.pipeline import REPO, InputFile, Inputs, analyze, build_rows, default_inputs, prepare


def _inputs(args) -> Inputs:
    d = default_inputs()
    return Inputs(
        baseline=InputFile.from_path(args.baseline) if args.baseline else d.baseline,
        revised=InputFile.from_path(args.revised) if args.revised else d.revised,
        register=InputFile.from_path(args.register) if args.register else d.register,
    )


def cmd_analyze(args) -> int:
    prep = prepare(_inputs(args))
    print(f"Baseline: {prep.inputs.baseline.name} ({prep.baseline.revision})")
    print(f"Revised:  {prep.inputs.revised.name} ({prep.revised.revision})")
    print(f"Register: {prep.inputs.register.name} ({len(prep.register.tests)} tests)\n")
    for c in prep.diff.requirement_changes:
        nums = ", ".join(f"{n.old_text or '-'} -> {n.new_text or '-'}" for n in c.numeric_changes)
        print(f"  {c.req_id}: {c.change_type.value}" + (f" ({nums})" if nums else ""))
    if not prep.diff.requirement_changes:
        print("  no requirement changes")

    outcome = analyze(prep, mode=args.mode)
    print(f"\n{outcome.source_text}\n")
    for row in build_rows(prep, outcome):
        a = row.assessment
        if a is None:
            print(f"  {row.test.test_id}  not analysed")
            continue
        actions = ", ".join(x.value + ("*" if x in row.actions_from_code else "") for x in a.required_actions)
        print(f"  {row.test.test_id}  {a.status.value:20s} {a.confidence.value:6s} [{actions}]")
        for w in row.warnings:
            print(f"           warning: {w}")
    print("\n  * set by the application from the register links, not by the model")
    print("  Recommendations only: final approval belongs to the authorized owner.")

    if args.report:
        from vcu_impact.report import build_report, render_html, render_markdown

        data = build_report(prep, outcome, build_rows(prep, outcome))
        path = Path(args.report)
        text = render_markdown(data) if path.suffix.lower() == ".md" else render_html(data)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print(f"\nWrote report {path}")

    if args.json:
        payload = {
            "inputs": {k: {"name": f.name, "sha256": f.sha256} for k, f in vars(prep.inputs).items()},
            "diff": prep.diff.model_dump(mode="json"),
            "outcome": {
                "mode": outcome.mode,
                "source": outcome.source_text,
                "run": outcome.run.model_dump(mode="json") if outcome.run else None,
            },
        }
        Path(args.json).write_text(json.dumps(payload, indent=1), encoding="utf-8")
        print(f"\nWrote {args.json}")
    return 0


def main(argv: list[str] | None = None) -> int:
    load_dotenv(REPO / ".env")
    p = argparse.ArgumentParser(prog="vcu-impact", description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("analyze", help="diff two specs and assess the register")
    a.add_argument("--baseline", help="baseline spec .docx (default: provided file)")
    a.add_argument("--revised", help="revised spec .docx (default: provided file)")
    a.add_argument("--register", help="test register .xlsx (default: provided file)")
    a.add_argument(
        "--mode",
        choices=["auto", "replay", "live"],
        default="auto",
        help="auto: recording if available, else the configured model (default)",
    )
    a.add_argument("--report", help="write the impact report to this file (.html or .md)")
    a.add_argument("--json", help="also write the full result to this JSON file")
    args = p.parse_args(argv)
    return {"analyze": cmd_analyze}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
