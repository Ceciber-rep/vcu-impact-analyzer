"""LLM evaluation harness.

    uv run python eval/evaluate.py build [--force]    # generate scenario .docx/.xlsx files (skips existing)
    uv run python eval/evaluate.py list-models        # show models each configured provider offers
    uv run python eval/evaluate.py run [--only NAME]  # run all models x scenarios (resumable)
    uv run python eval/evaluate.py score [--version v3] [--labels v2]
        # -> eval/results/<version>/summary_raw*.{json,md} and summary_postcheck*.{json,md}
    uv run python eval/evaluate.py decide [--version v3] [--view raw]   # the pre-registered decision rule

Every model receives the same system prompt, the same input and the same schema.
Raw outputs are stored under eval/results/<version>/<model>/ so scores can be re-computed
and individual answers inspected. Scoring has two views that are never mixed:
  raw        the statuses exactly as the model returned them;
  postcheck  the same stored output after the application's post-check (analysis.post_check).
Held-out scenarios (`held_out: true` in dataset.yaml) are scored separately from the original cells.
Existing summary files are never overwritten.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import traceback
from copy import copy
from functools import cache
from pathlib import Path

import yaml
from dotenv import load_dotenv
from openpyxl import load_workbook

from vcu_impact import spec_editor
from vcu_impact.analysis import approval_language, post_check, run_analysis
from vcu_impact.diff import diff_specs
from vcu_impact.llm import PROVIDERS, LLMClient, LLMConfig, LLMError
from vcu_impact.models import LLMImpactResult
from vcu_impact.pipeline import InputFile, Inputs, Prepared, prepare
from vcu_impact.prompt import PROMPT_VERSION
from vcu_impact.register_parser import _TEST_COLUMNS, _find_header, parse_register
from vcu_impact.spec_parser import parse_spec

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "eval"
INPUT = ROOT / "data" / "input"
SCEN_DIR = EVAL / "scenarios"
RESULTS = EVAL / "results"
CODES = {"D": "directly_affected", "P": "possibly_affected", "R": "needs_human_review", "N": "not_affected"}
SHORT = {v: k for k, v in CODES.items()}
CONSISTENCY_SCENARIO, CONSISTENCY_REPS = "S1", 3


def load_dataset() -> dict:
    data = yaml.safe_load((EVAL / "dataset.yaml").read_text())
    for sc in data["scenarios"]:
        for tid, label in sc["tests"].items():
            if isinstance(label, str):
                label = data["defaults"][label]
            sc["tests"][tid] = {
                "accept": [CODES[c] for c in label["accept"]],
                "preferred": CODES[label["preferred"]],
                "critical": bool(label.get("critical", False)),
                "why": label.get("why", ""),
                "accept_from_v2": [CODES[c] for c in label.get("accept_from_v2", [])],
                "actions": label.get("actions", {}),
                "related": label.get("related", {}),
            }
    return data


def original_scenarios(data: dict) -> list[dict]:
    return [sc for sc in data["scenarios"] if not sc.get("held_out")]


def held_out_scenarios(data: dict) -> list[dict]:
    return [sc for sc in data["scenarios"] if sc.get("held_out")]


def scenario_path(sc: dict) -> Path:
    """The revised specification of a scenario."""
    return INPUT / "VCU_Spec_Revised.docx" if sc.get("source") == "revised" else SCEN_DIR / f"{sc['id']}.docx"


def register_path(sc: dict) -> Path:
    """The test register of a scenario: the provided one unless the scenario edits it."""
    return SCEN_DIR / f"{sc['id']}_register.xlsx" if sc.get("register_edits") else INPUT / "VCU_Test_Register.xlsx"


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------


def build_register(sc: dict, out: Path) -> None:
    """Apply a scenario's register edits to a copy of the provided register (harness only)."""
    wb = load_workbook(INPUT / "VCU_Test_Register.xlsx")
    ws = next(w for w in wb.worksheets if _find_header(w, _TEST_COLUMNS, ("test_id", "reference"))[0])
    header, cols = _find_header(ws, _TEST_COLUMNS, ("test_id", "reference"))
    id_col = cols["test_id"] + 1

    def last_test_row() -> int:
        return max(r for r in range(header + 1, ws.max_row + 1) if ws.cell(r, id_col).value)

    for e in sc["register_edits"]:
        if e["op"] == "set_link":
            row = next(r for r in range(header + 1, ws.max_row + 1) if ws.cell(r, id_col).value == e["test"])
            ws.cell(row, cols["reference"] + 1).value = e["value"]
        elif e["op"] == "add_test":
            prev, new = last_test_row(), last_test_row() + 1
            values = {
                "test_id": e["test_id"],
                "name": e["name"],
                "procedure": e["procedure"],
                "reference": e["link"],
                "result": e["result"],
                "owner": e["owner"],
                "last_run": e["last_run"],
                "comment": e["comment"],
            }
            for key, col in cols.items():
                cell = ws.cell(new, col + 1, values[key])
                cell._style = copy(ws.cell(prev, col + 1)._style)
        else:
            raise ValueError(f"Unknown register edit {e['op']!r}")
    wb.save(out)
    wb.close()


def cmd_build(args) -> None:
    SCEN_DIR.mkdir(exist_ok=True)
    baseline = INPUT / "VCU_Spec_Baseline.docx"
    for sc in load_dataset()["scenarios"]:
        if sc.get("register_edits"):
            out = register_path(sc)
            if args.force or not out.exists():
                build_register(sc, out)
                reg = parse_register(out, parse_spec(scenario_path(sc)), parse_spec(baseline))
                print(f"{sc['id']}: {out.relative_to(ROOT)} -> {len(reg.tests)} tests")
        if sc.get("source") == "revised":
            continue
        out = scenario_path(sc)
        if out.exists() and not args.force:
            continue
        base = INPUT / "VCU_Spec_Revised.docx" if sc.get("base") == "revised" else baseline
        doc = spec_editor.load(base)
        for e in sc["edits"]:
            match e["op"]:
                case "replace":
                    spec_editor.replace_in_requirement(doc, e["req"], e["old"], e["new"])
                case "set":
                    spec_editor.set_requirement(doc, e["req"], text=e.get("text"), title=e.get("title"))
                case "remove":
                    spec_editor.remove_requirement(doc, e["req"])
                case "add":
                    spec_editor.add_requirement(doc, e["after"], e["req"], e["title"], e["text"])
        label = f"Revision {sc['id']} | evaluation scenario"
        spec_editor.replace_everywhere(doc, "Revision A | baseline", label)
        spec_editor.replace_everywhere(doc, "Revision B | candidate change", label)
        spec_editor.replace_everywhere(
            doc,
            "Initial validation baseline for this exercise package. The team has completed an earlier "
            "bench campaign against this revision.",
            "Evaluation scenario: candidate change prepared for engineering assessment.",
        )
        out.write_bytes(spec_editor.to_bytes(doc))
        d = diff_specs(parse_spec(baseline), parse_spec(out))
        summary = ", ".join(f"{c.req_id} {c.change_type.value}" for c in d.requirement_changes)
        print(f"{sc['id']}: {out.relative_to(ROOT)} -> {summary}")


# ---------------------------------------------------------------------------
# list-models / run
# ---------------------------------------------------------------------------


def cmd_list_models(_args) -> None:
    from openai import OpenAI

    for name, preset in PROVIDERS.items():
        key_env = preset["key_env"]
        if name in ("openai_compatible",):
            continue
        try:
            if name == "ollama":
                import httpx

                tags = httpx.get(f"{preset['base_url']}/api/tags", timeout=5).json()
                print(f"[ollama] {[m['name'] for m in tags.get('models', [])]}")
                continue
            import os

            if not os.getenv(key_env):
                print(f"[{name}] skipped: {key_env} not set")
                continue
            ids = sorted(m.id for m in OpenAI(api_key=os.getenv(key_env), base_url=preset["base_url"]).models.list())
            print(f"[{name}] {len(ids)} models: {ids}")
        except Exception as exc:  # noqa: BLE001 - diagnostic command
            print(f"[{name}] error: {str(exc)[:200]}")


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name)


def cmd_run(args) -> None:
    models = yaml.safe_load((EVAL / "models.yaml").read_text())["models"]
    data = load_dataset()
    baseline_path = INPUT / "VCU_Spec_Baseline.docx"
    baseline = parse_spec(baseline_path)
    for m in models:
        if args.only and m["name"] != args.only:
            continue
        try:
            config = LLMConfig.from_env(provider=m["provider"], model=m["model"])
        except LLMError as exc:
            print(f"[{m['name']}] skipped: {exc}")
            continue
        if m.get("think") is not None:
            config.ollama_think = m["think"]
        client = LLMClient(config)
        out_dir = RESULTS / (args.out or PROMPT_VERSION) / _safe(m["name"])
        out_dir.mkdir(parents=True, exist_ok=True)
        for sc in data["scenarios"]:
            if args.scenarios and sc["id"] not in args.scenarios.split(","):
                continue
            revised = parse_spec(scenario_path(sc))
            diff = diff_specs(baseline, revised)
            register = parse_register(register_path(sc), revised, baseline)
            reps = CONSISTENCY_REPS if sc["id"] == CONSISTENCY_SCENARIO else 1
            for rep in range(1, reps + 1):
                path = out_dir / f"{sc['id']}_r{rep}.json"
                if path.exists() and not args.force:
                    previous_ok = json.loads(path.read_text()).get("ok")
                    if previous_ok or not args.retry_failed:
                        continue
                    _log_availability(out_dir, sc["id"], rep, json.loads(path.read_text())["error"])
                print(f"[{m['name']}] {sc['id']} rep {rep} ...", end=" ", flush=True)
                try:
                    run = _with_rate_limit_wait(run_analysis, client, diff, revised, register)
                    path.write_text(json.dumps({"ok": True, **run.model_dump(mode="json")}, indent=1))
                    print(f"ok {run.latency_s}s attempts={run.attempts} mode={run.structured_mode}", flush=True)
                except Exception as exc:  # noqa: BLE001 - recorded as a failed run
                    err = f"{type(exc).__name__}: {exc}"
                    if _is_rate_limit(err):
                        print(f"RATE LIMITED after waiting, stopping this model: {err[:200]}")
                        break
                    path.write_text(
                        json.dumps(
                            {"ok": False, "error": err[:2000], "trace": traceback.format_exc()[-2000:]}, indent=1
                        )
                    )
                    print(f"FAILED: {err[:200]}")
            else:
                continue
            break


def _with_rate_limit_wait(fn, *args, waits=(65, 130, 260)):
    """Retry on rate-limit errors; per-minute token caps clear after about a minute."""
    import time

    for wait in (*waits, None):
        try:
            return fn(*args)
        except Exception as exc:  # noqa: BLE001
            if wait is None or not _is_rate_limit(f"{type(exc).__name__}: {exc}"):
                raise
            print(f"(rate limited, waiting {wait}s)", end=" ", flush=True)
            time.sleep(wait)


def _is_rate_limit(err: str) -> bool:
    """Rate limits and temporary unavailability: wait and retry rather than fail.

    Groq reports an exhausted per-minute token budget as HTTP 413 ("Request too large ...
    on tokens per minute (TPM)") when one analysis alone uses about the whole 8000-token
    budget of gpt-oss-120b, so that wording counts as a rate limit too.
    """
    return bool(
        re.search(
            r"429|rate.?limit|quota|RESOURCE_EXHAUSTED|\b503\b|UNAVAILABLE|overloaded|tokens per minute|\bTPM\b",
            err,
            re.I,
        )
    )


def _log_availability(out_dir: Path, scenario: str, rep: int, error: str) -> None:
    """Keep a record of failed attempts that are re-run, for the availability metric."""
    log = out_dir / "availability_log.jsonl"
    with log.open("a") as f:
        f.write(json.dumps({"scenario": scenario, "rep": rep, "error": error[:300]}) + "\n")


# ---------------------------------------------------------------------------
# score
# ---------------------------------------------------------------------------


@cache
def _prepared_cached(spec: str, register: str) -> Prepared:
    return prepare(
        Inputs(
            baseline=InputFile.from_path(INPUT / "VCU_Spec_Baseline.docx"),
            revised=InputFile.from_path(spec),
            register=InputFile.from_path(register),
        )
    )


def _prepared(sc: dict) -> Prepared:
    return _prepared_cached(str(scenario_path(sc)), str(register_path(sc)))


def _model_result(run: dict) -> dict:
    """The stored result with the application's own status corrections undone.

    Runs made after the rewording safety net existed store the post-checked result and list
    each correction in ``adjustments``; reverting them gives back the model's own statuses
    (plus any fill-in for omitted tests). Older runs have no adjustments and are returned as stored.
    """
    result = json.loads(json.dumps(run["result"]))
    original = {x["test_id"]: x["original_status"] for x in run.get("adjustments", [])}
    for a in result["assessments"]:
        if a["test_id"] in original:
            a["status"] = original[a["test_id"]]
    return result


def _assessments(run: dict, sc: dict, postcheck: bool) -> tuple[dict[str, dict], list[dict]]:
    """Per-test assessments of one stored run, and the adjustments made, for the chosen view.

    raw        the model's own statuses (plus any fill-in for omitted tests), never post-checked;
    postcheck  the same output after analysis.post_check, as the application applies it now.
    """
    result = _model_result(run)
    if not postcheck:
        return {a["test_id"]: a for a in result["assessments"]}, []
    for a in result["assessments"]:
        a.setdefault("required_actions", ["none"])  # prompt v1 had no such field
    prep = _prepared(sc)
    checked = post_check(LLMImpactResult.model_validate(result), prep.diff, prep.register)
    return (
        {a.test_id: a.model_dump(mode="json") for a in checked.result.assessments},
        [x.model_dump(mode="json") for x in checked.adjustments],
    )


def _check_constraint(constraint: dict, got: set[str]) -> bool:
    return set(constraint.get("must", [])) <= got and not (set(constraint.get("must_not", [])) & got)


def score_model(model_dir: Path, scenarios: list[dict], version: str = PROMPT_VERSION, postcheck: bool = False) -> dict:
    """Score one model's stored runs on ``scenarios``.

    ``version`` selects the label revision (v1 = original labels; later versions also accept
    the ``accept_from_v2`` statuses). ``postcheck`` selects the view, see ``_assessments``.
    """
    s = {
        "action_total": 0,
        "action_correct": 0,
        "action_failures": [],
        "related_total": 0,
        "related_correct": 0,
        "related_failures": [],
        "review_noise": 0,
        "runs": 0,
        "failed_runs": 0,
        "valid_first_attempt": 0,
        "judgments": 0,
        "lenient_correct": 0,
        "strict_correct": 0,
        "critical_cells": sum(c["critical"] for sc in scenarios for c in sc["tests"].values()),
        "critical_total": 0,
        "critical_correct": 0,
        "missed_impacts": 0,
        "missed_impact_cells": [],
        "over_flags": 0,
        "omitted_tests": 0,
        "approval_hits": 0,
        "adjustments": [],
        "latencies": [],
        "completion_tokens": [],
        "errors": [],
        "per_scenario": {},
        "critical_failures": [],
        "consistency": None,
        "structured_modes": set(),
        "valid_scenarios": [],
    }
    s1_statuses = []
    for sc in scenarios:
        reps = CONSISTENCY_REPS if sc["id"] == CONSISTENCY_SCENARIO else 1
        for rep in range(1, reps + 1):
            f = model_dir / f"{sc['id']}_r{rep}.json"
            if not f.exists():
                continue
            run = json.loads(f.read_text())
            s["runs"] += 1
            if not run["ok"]:
                s["failed_runs"] += 1
                s["errors"].append(f"{sc['id']} r{rep}: {run['error'][:160]}")
                if rep == 1:
                    s["per_scenario"][sc["id"]] = "failed"
                continue
            rejected = any("provider rejected" in w or "fell back" in w for w in run["warnings"])
            s["valid_first_attempt"] += run["attempts"] == 1 and not rejected
            s["latencies"].append(run["latency_s"])
            if run.get("completion_tokens"):
                s["completion_tokens"].append(run["completion_tokens"])
            s["structured_modes"].add(run.get("structured_mode", ""))
            s["omitted_tests"] += sum("returned no assessment" in w for w in run["warnings"])
            pred, adjustments = _assessments(run, sc, postcheck)
            text = " ".join(a["reason"] + " " + a["recommended_action"] for a in pred.values())
            s["approval_hits"] += len(approval_language(text))
            if sc["id"] == CONSISTENCY_SCENARIO:
                s1_statuses.append({t: pred[t]["status"] for t in pred})
            if rep != 1:
                continue  # accuracy uses the first repetition only
            s["valid_scenarios"].append(sc["id"])
            s["adjustments"] += [f"{sc['id']} {x['test_id']}" for x in adjustments]
            ok_count = 0
            for tid, label in sc["tests"].items():
                got = pred.get(tid, {}).get("status")
                s["judgments"] += 1
                accept = label["accept"] + (label["accept_from_v2"] if version != "v1" else [])
                lenient = got in accept
                ok_count += lenient
                s["lenient_correct"] += lenient
                s["strict_correct"] += got == label["preferred"]
                if "not_affected" not in accept and got == "not_affected":
                    s["missed_impacts"] += 1
                    s["missed_impact_cells"].append(f"{sc['id']} {tid}")
                if "directly_affected" not in accept and got == "directly_affected":
                    s["over_flags"] += 1
                if label["critical"]:
                    s["critical_total"] += 1
                    s["critical_correct"] += lenient
                    if not lenient:
                        expected = "/".join(SHORT[a] for a in accept)
                        got_code = SHORT.get(got, got)
                        s["critical_failures"].append(f"{sc['id']} {tid}: got {got_code}, expected {expected}")
                pred_actions = pred.get(tid, {}).get("required_actions", [])
                if label["preferred"] == "not_affected" and (
                    got == "needs_human_review" or "owner_decision" in pred_actions
                ):
                    s["review_noise"] += 1
                if version != "v1" and label["actions"]:
                    ok = _check_constraint(label["actions"], set(pred_actions))
                    s["action_total"] += 1
                    s["action_correct"] += ok
                    if not ok:
                        s["action_failures"].append(
                            f"{sc['id']} {tid}: got {sorted(pred_actions)}, rule {label['actions']}"
                        )
                if label["related"]:
                    got_related = set(pred.get(tid, {}).get("related_requirements", []))
                    ok = _check_constraint(label["related"], got_related)
                    s["related_total"] += 1
                    s["related_correct"] += ok
                    if not ok:
                        s["related_failures"].append(
                            f"{sc['id']} {tid}: got {sorted(got_related)}, rule {label['related']}"
                        )
            s["per_scenario"][sc["id"]] = f"{ok_count}/{len(sc['tests'])}"
    log = model_dir / "availability_log.jsonl"
    s["service_errors"] = s["failed_runs"] + (len(log.read_text().splitlines()) if log.exists() else 0)
    if len(s1_statuses) >= 2:
        tests = s1_statuses[0].keys()
        stable = sum(all(r.get(t) == s1_statuses[0][t] for r in s1_statuses) for t in tests)
        s["consistency"] = f"{stable}/{len(tests)} over {len(s1_statuses)} runs"
    s["structured_modes"] = sorted(s["structured_modes"] - {""})
    s["complete"] = {sc["id"] for sc in scenarios} <= set(s["valid_scenarios"])
    return s


def _model_dirs(version: str):
    models = yaml.safe_load((EVAL / "models.yaml").read_text())["models"]
    for m in models:
        d = RESULTS / version / _safe(m["name"])
        if d.exists():
            yield m, d


def cmd_score(args) -> None:
    data = load_dataset()
    base = RESULTS / args.version
    labels = args.labels or args.version  # label revision: v1 labels, or v2+ with the relabelled cells
    suffix = "" if labels == args.version else f"_labels-{labels}"
    sets = [("original", original_scenarios(data)), ("held_out", held_out_scenarios(data))]
    for view in ("raw", "postcheck"):
        summaries: dict[str, dict] = {}
        for kind, scenarios in sets:
            if not scenarios:
                continue
            summ = {
                m["name"]: {
                    "provider": m["provider"],
                    "model": m["model"],
                    **score_model(d, scenarios, labels, view == "postcheck"),
                }
                for m, d in _model_dirs(args.version)
            }
            if kind == "held_out" and not any(x["runs"] for x in summ.values()):
                continue  # nothing run on the held-out scenarios yet
            summaries[kind] = summ
        (base / f"summary_{view}{suffix}.json").write_text(json.dumps(summaries, indent=1))
        md = render_view(view, summaries, data, args.version, labels)
        (base / f"summary_{view}{suffix}.md").write_text(md)
        print(md)


def _pct(a, b):
    return f"{100 * a / b:.0f}% ({a}/{b})" if b else "n/a"


VIEW_TITLE = {
    "raw": "Raw model statuses (exactly as the model returned them)",
    "postcheck": "After the application's post-check (same stored outputs, rewording safety net applied)",
}


def render_view(view: str, summaries: dict, data: dict, version: str, labels: str) -> str:
    lines = [f"# {VIEW_TITLE[view]}", "", f"Prompt version {version}, labels {labels}.", ""]
    if "original" in summaries:
        lines += ["## Original scenarios (S1 to S7)", ""]
        lines += render_markdown(summaries["original"], original_scenarios(data), view == "postcheck")
    if "held_out" in summaries:
        n = sum(len(sc["tests"]) for sc in held_out_scenarios(data))
        lines += ["", f"## Held-out scenarios ({n} cells, scored separately)", ""]
        lines += render_markdown(summaries["held_out"], held_out_scenarios(data), view == "postcheck")
    return "\n".join(lines) + "\n"


def render_markdown(summary: dict, scenarios: list[dict], postcheck: bool) -> list[str]:
    head = (
        "| Model | Runs ok | Valid 1st try | Lenient acc. | Strict acc. | Critical cases | Missed impacts "
        "| Over-flags (D) | Unneeded review flags | Omitted tests | Approval wording | S1 consistency "
        "| Median latency | Median output tokens | Service errors |"
    )
    cols = 15
    if postcheck:
        head += " Post-check adjustments |"
        cols += 1
    lines = [head, "|" + "---|" * cols]
    for name, s in summary.items():
        ok = s["runs"] - s["failed_runs"]
        lat = sorted(s["latencies"])
        tok = sorted(s["completion_tokens"])
        row = (
            f"| {name} | {ok}/{s['runs']} | {_pct(s['valid_first_attempt'], ok)} | "
            f"{_pct(s['lenient_correct'], s['judgments'])} | {_pct(s['strict_correct'], s['judgments'])} | "
            f"{_pct(s['critical_correct'], s['critical_total'])} | {s['missed_impacts']} | {s['over_flags']} | "
            f"{s['review_noise']} | {s['omitted_tests']} | "
            f"{s['approval_hits']} | {s['consistency'] or 'n/a'} | "
            f"{f'{lat[len(lat) // 2]:.0f} s' if lat else 'n/a'} | {tok[len(tok) // 2] if tok else 'n/a'} | "
            f"{s['service_errors']} |"
        )
        if postcheck:
            row += f" {len(s['adjustments'])} |"
        lines.append(row)
    lines += [
        "",
        "Per-scenario lenient score (first repetition):",
        "",
        "| Model | " + " | ".join(sc["id"] for sc in scenarios) + " |",
        "|---|" + "---|" * len(scenarios),
    ]
    for name, s in summary.items():
        cells = " | ".join(s["per_scenario"].get(sc["id"], "-") for sc in scenarios)
        lines.append(f"| {name} | {cells} |")
    if any(s.get("action_total") for s in summary.values()):
        lines += ["", "Required actions (labelled cases, first repetition):", ""]
        for name, s in summary.items():
            lines.append(
                f"- **{name}**: {_pct(s['action_correct'], s['action_total'])}; failures: "
                + ("; ".join(s["action_failures"]) or "none")
            )
    if any(s.get("related_total") for s in summary.values()):
        lines += ["", "Related requirements (labelled cases, first repetition):", ""]
        for name, s in summary.items():
            lines.append(
                f"- **{name}**: {_pct(s['related_correct'], s['related_total'])}; failures: "
                + ("; ".join(s["related_failures"]) or "none")
            )
    if postcheck:
        lines += ["", "Statuses changed by the post-check:", ""]
        for name, s in summary.items():
            lines.append(f"- **{name}**: " + (", ".join(s["adjustments"]) or "none"))
    lines += ["", "Missed impacts (not_affected where the label does not allow it):", ""]
    for name, s in summary.items():
        lines.append(f"- **{name}**: " + (", ".join(s["missed_impact_cells"]) or "none"))
    lines += ["", "Critical-case failures:", ""]
    for name, s in summary.items():
        lines.append(f"- **{name}**: " + ("; ".join(s["critical_failures"]) or "none"))
        for e in s["errors"]:
            lines.append(f"  - run error: {e}")
    return lines


# ---------------------------------------------------------------------------
# decide: the pre-registered decision rule (docs/llm_evaluation.md, section 8.1)
# ---------------------------------------------------------------------------

PRIMARY = "groq-qwen3.8-27b"


def decision_rows(data: dict, version: str, postcheck: bool = True) -> dict[str, dict]:
    """Critical failures and missed impacts over original + held-out cells (post-check applied by default)."""
    scenarios = data["scenarios"]
    critical_cells = sum(c["critical"] for sc in scenarios for c in sc["tests"].values())
    out = {}
    for m, d in _model_dirs(version):
        o = score_model(d, original_scenarios(data), version, postcheck=postcheck)
        h = score_model(d, held_out_scenarios(data), version, postcheck=postcheck)
        out[m["name"]] = {
            "critical_failures": critical_cells - (o["critical_correct"] + h["critical_correct"]),
            "critical_cells": critical_cells,
            "missed_impacts": o["missed_impacts"] + h["missed_impacts"],
            "missing_scenarios": sorted(
                {sc["id"] for sc in scenarios} - set(o["valid_scenarios"]) - set(h["valid_scenarios"])
            ),
            "failed_cells": o["critical_failures"] + h["critical_failures"],
            "missed_cells": o["missed_impact_cells"] + h["missed_impact_cells"],
        }
    return out


def cmd_decide(args) -> None:
    data = load_dataset()
    postcheck = args.view == "postcheck"
    rows = decision_rows(data, args.version, postcheck)
    if PRIMARY not in rows:
        sys.exit(f"No results for the primary model {PRIMARY!r} under {args.version}.")
    prim = rows[PRIMARY]
    lines = [
        "# Decision rule outcome"
        + ("" if postcheck else " (raw statuses: INFORMATIONAL, not the pre-registered rule)"),
        "",
        f"Prompt version {args.version}; "
        + ("post-check applied (as pre-registered)" if postcheck else "raw model statuses, post-check NOT applied")
        + f"; original + held-out cells ({prim['critical_cells']} critical cells).",
        "",
        "Rule: the primary model stays unless a challenger has strictly fewer critical failures AND zero missed "
        "impacts. Ties go to the primary. A scenario without a valid run counts all its critical cells as failures.",
        "",
        "| Model | Critical failures | Missed impacts | Missing scenarios | Replaces the primary? |",
        "|---|---|---|---|---|",
    ]
    winners = []
    for name, r in rows.items():
        if name == PRIMARY:
            verdict = "(primary)"
        elif r["missing_scenarios"]:
            verdict = f"no: missing valid runs for {', '.join(r['missing_scenarios'])}"
        elif r["critical_failures"] < prim["critical_failures"] and r["missed_impacts"] == 0:
            verdict = "yes"
            winners.append(name)
        else:
            why = []
            if r["critical_failures"] >= prim["critical_failures"]:
                why.append("not strictly fewer critical failures")
            if r["missed_impacts"]:
                why.append(f"{r['missed_impacts']} missed impact(s)")
            verdict = "no: " + "; ".join(why)
        lines.append(
            f"| {name} | {r['critical_failures']} | {r['missed_impacts']} | "
            f"{', '.join(r['missing_scenarios']) or '-'} | {verdict} |"
        )
    lines += ["", "Cells behind the numbers:", ""]
    for name, r in rows.items():
        lines.append(f"- **{name}** critical failures: {'; '.join(r['failed_cells']) or 'none'}")
        lines.append(f"  - missed impacts: {', '.join(r['missed_cells']) or 'none'}")
    lines += [
        "",
        f"**Outcome: {winners[0] + ' replaces ' + PRIMARY if len(winners) == 1 else PRIMARY + ' stays primary'}.**"
        if len(winners) <= 1
        else f"**Outcome: several challengers qualify ({', '.join(winners)}); the rule does not choose between them.**",
    ]
    md = "\n".join(lines) + "\n"
    (RESULTS / args.version / ("decision.md" if postcheck else "decision_raw.md")).write_text(md)
    print(md)


def main() -> None:
    load_dotenv(ROOT / ".env")
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--force", action="store_true", help="regenerate scenario files that already exist")
    sub.add_parser("list-models")
    r = sub.add_parser("run")
    r.add_argument("--only")
    r.add_argument("--force", action="store_true")
    r.add_argument("--retry-failed", action="store_true", help="re-run scenarios whose previous run failed")
    r.add_argument("--out", help="results sub-folder under eval/results (default: the prompt version)")
    r.add_argument("--scenarios", help="comma-separated scenario ids to run, e.g. S1,S2,S5")
    sc = sub.add_parser("score")
    sc.add_argument("--version", default=PROMPT_VERSION, help="prompt version whose results to score")
    sc.add_argument("--labels", help="label revision to apply (default: same as --version; v1 = original labels)")
    d = sub.add_parser("decide")
    d.add_argument("--version", default=PROMPT_VERSION)
    d.add_argument(
        "--view",
        choices=["postcheck", "raw"],
        default="postcheck",
        help="postcheck is the pre-registered rule; raw is shown for transparency only",
    )
    args = p.parse_args()
    {"build": cmd_build, "list-models": cmd_list_models, "run": cmd_run, "score": cmd_score, "decide": cmd_decide}[
        args.cmd
    ](args)


if __name__ == "__main__":
    sys.exit(main())
