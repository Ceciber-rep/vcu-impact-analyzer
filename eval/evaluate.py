"""LLM evaluation harness.

    uv run python eval/evaluate.py build              # generate scenario .docx files
    uv run python eval/evaluate.py list-models        # show models each configured provider offers
    uv run python eval/evaluate.py run [--only NAME]  # run all models x scenarios (resumable)
    uv run python eval/evaluate.py score [--version v1]  # -> eval/results/<version>/summary.json + .md

Every model receives the same system prompt, the same input and the same schema.
Raw outputs are stored under eval/results/<model>/ so scores can be re-computed
and individual answers inspected.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import traceback
from pathlib import Path

import yaml
from dotenv import load_dotenv

from vcu_impact import spec_editor
from vcu_impact.analysis import approval_language, run_analysis
from vcu_impact.diff import diff_specs
from vcu_impact.llm import PROVIDERS, LLMClient, LLMConfig, LLMError
from vcu_impact.prompt import PROMPT_VERSION
from vcu_impact.register_parser import parse_register
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
            }
    return data


def scenario_path(sc: dict) -> Path:
    return INPUT / "VCU_Spec_Revised.docx" if sc.get("source") == "revised" else SCEN_DIR / f"{sc['id']}.docx"


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------


def cmd_build(_args) -> None:
    SCEN_DIR.mkdir(exist_ok=True)
    baseline = INPUT / "VCU_Spec_Baseline.docx"
    for sc in load_dataset()["scenarios"]:
        if sc.get("source") == "revised":
            continue
        doc = spec_editor.load(baseline)
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
        spec_editor.replace_everywhere(
            doc,
            "Initial validation baseline for this exercise package. The team has completed an earlier "
            "bench campaign against this revision.",
            "Evaluation scenario: candidate change prepared for engineering assessment.",
        )
        out = scenario_path(sc)
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
        out_dir = RESULTS / PROMPT_VERSION / _safe(m["name"])
        out_dir.mkdir(parents=True, exist_ok=True)
        for sc in data["scenarios"]:
            revised = parse_spec(scenario_path(sc))
            diff = diff_specs(baseline, revised)
            register = parse_register(INPUT / "VCU_Test_Register.xlsx", revised, baseline)
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
    """Rate limits and temporary unavailability: wait and retry rather than fail."""
    return bool(re.search(r"429|rate.?limit|quota|RESOURCE_EXHAUSTED|\b503\b|UNAVAILABLE|overloaded", err, re.I))


def _log_availability(out_dir: Path, scenario: str, rep: int, error: str) -> None:
    """Keep a record of failed attempts that are re-run, for the availability metric."""
    log = out_dir / "availability_log.jsonl"
    with log.open("a") as f:
        f.write(json.dumps({"scenario": scenario, "rep": rep, "error": error[:300]}) + "\n")


# ---------------------------------------------------------------------------
# score
# ---------------------------------------------------------------------------


def score_model(model_dir: Path, data: dict, version: str = PROMPT_VERSION) -> dict:
    """Score one model's runs. ``version`` selects which label revision applies."""
    s = {
        "action_total": 0,
        "action_correct": 0,
        "action_failures": [],
        "review_noise": 0,
        "runs": 0,
        "failed_runs": 0,
        "valid_first_attempt": 0,
        "judgments": 0,
        "lenient_correct": 0,
        "strict_correct": 0,
        "critical_total": 0,
        "critical_correct": 0,
        "missed_impacts": 0,
        "over_flags": 0,
        "omitted_tests": 0,
        "approval_hits": 0,
        "postcheck_warnings": 0,
        "latencies": [],
        "completion_tokens": [],
        "errors": [],
        "per_scenario": {},
        "critical_failures": [],
        "consistency": None,
        "structured_modes": set(),
    }
    s1_statuses = []
    for sc in data["scenarios"]:
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
            s["postcheck_warnings"] += sum(
                "approval-like" not in w for w in run["warnings"] if not w.startswith("attempt")
            )
            pred = {a["test_id"]: a for a in run["result"]["assessments"]}
            text = " ".join(a["reason"] + " " + a["recommended_action"] for a in pred.values())
            s["approval_hits"] += len(approval_language(text))
            if sc["id"] == CONSISTENCY_SCENARIO:
                s1_statuses.append({t: pred[t]["status"] for t in pred})
            if rep != 1:
                continue  # accuracy uses the first repetition only
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
                    acts = set(pred.get(tid, {}).get("required_actions", []))
                    must, must_not = set(label["actions"].get("must", [])), set(label["actions"].get("must_not", []))
                    ok = must <= acts and not (must_not & acts)
                    s["action_total"] += 1
                    s["action_correct"] += ok
                    if not ok:
                        s["action_failures"].append(f"{sc['id']} {tid}: got {sorted(acts)}, rule {label['actions']}")
            s["per_scenario"][sc["id"]] = f"{ok_count}/{len(sc['tests'])}"
    log = model_dir / "availability_log.jsonl"
    s["service_errors"] = s["failed_runs"] + (len(log.read_text().splitlines()) if log.exists() else 0)
    if len(s1_statuses) >= 2:
        tests = s1_statuses[0].keys()
        stable = sum(all(r.get(t) == s1_statuses[0][t] for r in s1_statuses) for t in tests)
        s["consistency"] = f"{stable}/{len(tests)} over {len(s1_statuses)} runs"
    s["structured_modes"] = sorted(s["structured_modes"] - {""})
    return s


def cmd_score(args) -> None:
    data = load_dataset()
    models = yaml.safe_load((EVAL / "models.yaml").read_text())["models"]
    base = RESULTS / args.version
    labels = args.labels or args.version  # label revision: v1 labels, or v2+ with the relabelled cells
    suffix = "" if labels == args.version else f"_labels-{labels}"
    summary = {}
    for m in models:
        d = base / _safe(m["name"])
        if d.exists():
            summary[m["name"]] = {"provider": m["provider"], "model": m["model"], **score_model(d, data, labels)}
    (base / f"summary{suffix}.json").write_text(json.dumps(summary, indent=1))
    md = render_markdown(summary, data)
    (base / f"summary{suffix}.md").write_text(md)
    print(md)


def _pct(a, b):
    return f"{100 * a / b:.0f}% ({a}/{b})" if b else "n/a"


def render_markdown(summary: dict, data: dict) -> str:
    lines = [
        "| Model | Runs ok | Valid 1st try | Lenient acc. | Strict acc. | Critical cases | Missed impacts "
        "| Over-flags (D) | Unneeded review flags | Omitted tests | Approval wording | S1 consistency "
        "| Median latency | Median output tokens "
        "| Service errors |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for name, s in summary.items():
        ok = s["runs"] - s["failed_runs"]
        lat = sorted(s["latencies"])
        tok = sorted(s["completion_tokens"])
        lines.append(
            f"| {name} | {ok}/{s['runs']} | {_pct(s['valid_first_attempt'], ok)} | "
            f"{_pct(s['lenient_correct'], s['judgments'])} | {_pct(s['strict_correct'], s['judgments'])} | "
            f"{_pct(s['critical_correct'], s['critical_total'])} | {s['missed_impacts']} | {s['over_flags']} | "
            f"{s['review_noise']} | {s['omitted_tests']} | "
            f"{s['approval_hits']} | {s['consistency'] or 'n/a'} | "
            f"{f'{lat[len(lat) // 2]:.0f} s' if lat else 'n/a'} | {tok[len(tok) // 2] if tok else 'n/a'} | "
            f"{s['service_errors']} |"
        )
    lines += [
        "",
        "Per-scenario lenient score (first repetition):",
        "",
        "| Model | " + " | ".join(sc["id"] for sc in data["scenarios"]) + " |",
        "|---|" + "---|" * len(data["scenarios"]),
    ]
    for name, s in summary.items():
        cells = " | ".join(s["per_scenario"].get(sc["id"], "-") for sc in data["scenarios"])
        lines.append(f"| {name} | {cells} |")
    if any(s.get("action_total") for s in summary.values()):
        lines += ["", "Required actions (labelled cases, first repetition):", ""]
        for name, s in summary.items():
            lines.append(
                f"- **{name}**: {_pct(s['action_correct'], s['action_total'])}; failures: "
                + ("; ".join(s["action_failures"]) or "none")
            )
    lines += ["", "Critical-case failures:", ""]
    for name, s in summary.items():
        lines.append(f"- **{name}**: " + ("; ".join(s["critical_failures"]) or "none"))
        for e in s["errors"]:
            lines.append(f"  - run error: {e}")
    return "\n".join(lines) + "\n"


def main() -> None:
    load_dotenv(ROOT / ".env")
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build")
    sub.add_parser("list-models")
    r = sub.add_parser("run")
    r.add_argument("--only")
    r.add_argument("--force", action="store_true")
    r.add_argument("--retry-failed", action="store_true", help="re-run scenarios whose previous run failed")
    sc = sub.add_parser("score")
    sc.add_argument("--version", default=PROMPT_VERSION, help="prompt version whose results to score")
    sc.add_argument("--labels", help="label revision to apply (default: same as --version; v1 = original labels)")
    args = p.parse_args()
    {"build": cmd_build, "list-models": cmd_list_models, "run": cmd_run, "score": cmd_score}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
