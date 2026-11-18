"""Phase 4 runner: the application as it runs in production (Groq primary, Gemini fallback), one call per case.

    uv run python eval/assess_run.py [--pause 65] [--only S1,N4]   # resumable; -> eval/results/assessment/app-groq-gemini/

Each case goes through ``pipeline.prepare`` and ``pipeline.analyze(mode="live")``, i.e. the same path as the UI's
"Run analysis" button, including the fallback. Cases: every scenario of dataset.yaml (S1-S10) and
dataset_assessment.yaml (N1-N6) once; 4 more repeats of S1 and N4; four perturbations of S1 and N4:
  P1 shuffled test-row order, P2 shuffled workshop notes, P3 harmless formatting (date format, trailing full
  stops, owner initials), P4 renamed test ids. Calls are paced (default 65 s) so that the Groq per-minute limit
  (F-002) does not dominate; the unpaced behaviour was measured in phase 1 (4 of 7 runs fell back).
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
from io import BytesIO
from pathlib import Path

import openpyxl
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))
load_dotenv(ROOT / ".env")
import evaluate as ev  # noqa: E402

from vcu_impact.pipeline import InputFile, Inputs, analyze, prepare  # noqa: E402

OUT = ev.RESULTS / "assessment" / "app-groq-gemini"
REPEAT_SCENARIOS = ("S1", "N4")


def _scenarios() -> dict[str, dict]:
    out = {}
    for ds in ("dataset.yaml", "dataset_assessment.yaml"):
        os.environ["VCU_EVAL_DATASET"] = ds
        for sc in ev.load_dataset()["scenarios"]:
            sc["_dataset"] = ds
            out[sc["id"]] = sc
    return out


def _register_rows(ws):
    return [r for r in range(1, ws.max_row + 1) if str(ws.cell(r, 1).value or "").startswith("TV-")]


def perturb_register(data: bytes, kind: str) -> bytes:
    wb = openpyxl.load_workbook(BytesIO(data))
    ws = wb["Test register"]
    rows = _register_rows(ws)
    rng = random.Random(7)
    if kind == "P1":
        values = [[ws.cell(r, c).value for c in range(1, ws.max_column + 1)] for r in rows]
        rng.shuffle(values)
        for r, vals in zip(rows, values, strict=True):
            for c, v in enumerate(vals, 1):
                ws.cell(r, c).value = v
    elif kind == "P2":
        notes = wb["Workshop notes"]
        nrows = [r for r in range(4, notes.max_row + 1) if notes.cell(r, 1).value]
        values = [[notes.cell(r, c).value for c in range(1, notes.max_column + 1)] for r in nrows]
        rng.shuffle(values)
        for r, vals in zip(nrows, values, strict=True):
            for c, v in enumerate(vals, 1):
                notes.cell(r, c).value = v
    elif kind == "P3":
        for r in rows:
            d = ws.cell(r, 7).value
            if d:
                y, m, dd = str(d)[:10].split("-")
                ws.cell(r, 7).value = f"{dd}/{m}/{y}"
            for c in (3, 8):
                v = ws.cell(r, c).value
                if v and not str(v).endswith("."):
                    ws.cell(r, c).value = f"{v}."
            if ws.cell(r, 6).value == "A.":
                ws.cell(r, 6).value = "A"
    elif kind == "P4":
        for r in rows:
            n = int(ws.cell(r, 1).value.split("-")[1])
            ws.cell(r, 1).value = f"QX-{n + 40:03d}"
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def build_cases(only: set[str] | None) -> list[dict]:
    scs = _scenarios()
    cases = [{"case": f"{sid}_r1", "scenario": sid, "kind": "base"} for sid in scs]
    for sid in REPEAT_SCENARIOS:
        cases += [{"case": f"{sid}_r{n}", "scenario": sid, "kind": "repeat"} for n in range(2, 6)]
    for sid in REPEAT_SCENARIOS:
        cases += [{"case": f"{k}_{sid}", "scenario": sid, "kind": k} for k in ("P1", "P2", "P3", "P4")]
    for c in cases:
        c["sc"] = scs[c["scenario"]]
    return [c for c in cases if not only or c["scenario"] in only]


def inputs_for(case: dict) -> Inputs:
    sc = case["sc"]
    os.environ["VCU_EVAL_DATASET"] = sc["_dataset"]
    reg = ev.register_path(sc).read_bytes()
    if case["kind"].startswith("P"):
        reg = perturb_register(reg, case["kind"])
    return Inputs(
        InputFile.from_path(ev.INPUT / "VCU_Spec_Baseline.docx"),
        InputFile.from_path(ev.scenario_path(sc)),
        InputFile(f"{sc['id']}_register.xlsx", reg),
    )


def redact(text: str) -> str:
    return re.sub(r"org_[a-z0-9]+", "org_REDACTED", text)


def run_case(case: dict) -> dict:
    prep = prepare(inputs_for(case))
    first_failure = ""
    for attempt in (1, 2):
        out = analyze(prep, mode="live")
        if out.run:
            run = out.run.model_dump(mode="json")
            run["warnings"] = [redact(w) for w in run["warnings"]]
            return {
                "ok": True,
                "case": case["case"],
                "scenario": case["scenario"],
                "kind": case["kind"],
                "served_by": out.run.model_label,
                "fallback_used": any(" failed: " in w for w in out.run.warnings),
                "first_attempt_failed": first_failure,
                **run,
            }
        first_failure = redact(out.reason)[:600]
        with (OUT / "availability_log.jsonl").open(
            "a"
        ) as log:  # every failed attempt, kept even if a later run succeeds
            log.write(
                json.dumps(
                    {"case": case["case"], "attempt": attempt, "at": time.strftime("%F %T"), "error": first_failure}
                )
                + "\n"
            )
        if attempt == 1:
            time.sleep(90)
    return {
        "ok": False,
        "case": case["case"],
        "scenario": case["scenario"],
        "kind": case["kind"],
        "error": first_failure,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--pause", type=int, default=65)
    p.add_argument("--only")
    args = p.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    cases = build_cases(set(args.only.split(",")) if args.only else None)
    todo = []
    for c in cases:
        f = OUT / f"{c['case']}.json"
        if not (f.exists() and json.loads(f.read_text()).get("ok")):
            todo.append(c)
    print(f"{len(todo)} of {len(cases)} cases to run", flush=True)
    for n, c in enumerate(todo):
        if n:
            time.sleep(args.pause)
        t0 = time.time()
        rec = run_case(c)
        (OUT / f"{c['case']}.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False))
        print(
            f"{c['case']}: ok={rec['ok']} by={rec.get('served_by', '-')} fallback={rec.get('fallback_used')} "
            f"{time.time() - t0:.0f}s {rec.get('error', '')[:100]}",
            flush=True,
        )


if __name__ == "__main__":
    main()
