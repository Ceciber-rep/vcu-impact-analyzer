"""Phase 4 analysis: accuracy, error categories, evidence grounding, consistency, reliability, calibration, nature.

    uv run python eval/assess_analyze.py   # reads eval/results/assessment/*; writes docs/assessment/results/phase4_*

Sources: the application path (Groq with Gemini fallback), the rule-only baseline, and the frozen v3 runs of the two
models on S1-S10 (read only). Two views are never mixed: raw (the model's own statuses) and post-check.
"""

from __future__ import annotations

import json
import math
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))
import assess_run as ar  # noqa: E402
import evaluate as ev  # noqa: E402

from vcu_impact.analysis import approval_language, post_check  # noqa: E402
from vcu_impact.models import LLMImpactResult  # noqa: E402
from vcu_impact.pipeline import prepare  # noqa: E402

R = ev.RESULTS
SOURCES = {
    "app (Groq, Gemini fallback)": R / "assessment" / "app-groq-gemini",
    "naive baseline (rules)": R / "assessment" / "naive-baseline",
    "v3 frozen: Groq qwen3.8-27b": R / "v3" / "groq-qwen3.8-27b",
    "v3 frozen: Gemini 3.5 Flash": R / "v3" / "gemini-3.5-flash",
}
OUTDIR = ROOT / "docs" / "assessment" / "results"
SC = ar._scenarios()
_PREP: dict[str, object] = {}


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def rate(k: int, n: int) -> str:
    lo, hi = wilson(k, n)
    return f"{k}/{n} = {100 * k / n:.0f}% (95% CI {100 * lo:.0f}-{100 * hi:.0f}%)" if n else "n/a"


def case_for(name: str) -> dict:
    m = re.match(r"(P\d)_(\w+)$", name)
    if m:
        return {"case": name, "scenario": m[2], "kind": m[1], "sc": SC[m[2]]}
    sid, rep = name.rsplit("_r", 1)
    return {"case": name, "scenario": sid, "kind": "base" if rep == "1" else "repeat", "sc": SC[sid]}


def prep_for(case: dict):
    if case["case"] not in _PREP:
        _PREP[case["case"]] = prepare(ar.inputs_for(case))
    return _PREP[case["case"]]


def load(src: Path) -> dict[str, dict]:
    out = {}
    for f in sorted(src.glob("*.json")):
        if f.name.startswith("summary") or f.name == "availability_log.jsonl":
            continue
        try:
            d = json.loads(f.read_text())
        except json.JSONDecodeError:
            continue
        if d.get("ok") and re.match(r"([PSN]\d+)(_r\d+|_[SN]\d+)?$", f.stem):
            out[f.stem] = d
    return out


def statuses(run: dict, case: dict, view: str) -> dict[str, dict]:
    result = ev._model_result(run)  # the model's own statuses (adjustments undone)
    for a in result["assessments"]:
        a.setdefault("required_actions", ["none"])
    if view == "raw":
        return {a["test_id"]: a for a in result["assessments"]}
    prep = prep_for(case)
    checked = post_check(LLMImpactResult.model_validate(result), prep.diff, prep.register)
    return {a.test_id: a.model_dump(mode="json") for a in checked.result.assessments}


# ---------------------------------------------------------------------------------------------------------------------
# cells
# ---------------------------------------------------------------------------------------------------------------------


def cells(records: dict[str, dict], view: str) -> list[dict]:
    out = []
    for name, run in records.items():
        case = case_for(name)
        if case["kind"] != "base":
            continue
        sc = case["sc"]
        try:
            pred = statuses(run, case, view)
        except Exception as exc:  # noqa: BLE001
            print("skip", name, exc)
            continue
        for tid, label in sc["tests"].items():
            a = pred.get(tid)
            got = a["status"] if a else None
            accept = label["accept"] + label["accept_from_v2"]
            out.append(
                {
                    "scenario": sc["id"],
                    "test": tid,
                    "got": got,
                    "accept": accept,
                    "preferred": label["preferred"],
                    "critical": label["critical"],
                    "why": label["why"],
                    "ok": got in accept,
                    "strict": got == label["preferred"],
                    "confidence": a.get("confidence") if a else None,
                    "actions": a.get("required_actions", []) if a else [],
                    "related": a.get("related_requirements", []) if a else [],
                    "label_actions": label["actions"],
                    "label_related": label["related"],
                    "served_by": run.get("served_by", run.get("model_label", "")),
                    "held_out": bool(sc.get("held_out")),
                    "dataset": "N" if sc["id"].startswith("N") else "S",
                }
            )
    return out


def summarize(cs: list[dict]) -> dict:
    crit = [c for c in cs if c["critical"]]
    missed = [c for c in cs if c["got"] == "not_affected" and "not_affected" not in c["accept"]]
    over = [c for c in cs if c["got"] == "directly_affected" and "directly_affected" not in c["accept"]]
    distinct = {(c["test"], tuple(sorted(c["accept"])), c["preferred"], c["why"]) for c in cs}
    distinct_crit = {(c["test"], tuple(sorted(c["accept"])), c["preferred"], c["why"]) for c in crit}
    return {
        "judgments": len(cs),
        "ok": sum(c["ok"] for c in cs),
        "strict": sum(c["strict"] for c in cs),
        "critical": len(crit),
        "critical_ok": sum(c["ok"] for c in crit),
        "missed": len(missed),
        "over_flags": len(over),
        "distinct_cells": len(distinct),
        "distinct_critical": len(distinct_crit),
        "distinct_critical_failing": len({(c["test"], c["why"]) for c in crit if not c["ok"]}),
    }


def category(c: dict) -> str:
    """Error category of one wrong cell (heuristic, from the label and the answer)."""
    why = c["why"].lower()
    if c["got"] == "not_affected" and "not_affected" not in c["accept"]:
        return "missed impact"
    if "clock" in why or "pedal level" in why or "not 80 ms" in why:
        return "arithmetic / clock / unit confusion"
    if c["got"] in ("directly_affected", "possibly_affected") and not set(c["accept"]) & {
        "directly_affected",
        "possibly_affected",
    }:
        return "over-flag"
    if c["got"] == "directly_affected" and "directly_affected" not in c["accept"]:
        return "over-flag"
    return "wrong status (other)"


# ---------------------------------------------------------------------------------------------------------------------
# evidence grounding
# ---------------------------------------------------------------------------------------------------------------------


def _flatten(o) -> list[str]:
    if isinstance(o, str):
        return [o]
    if isinstance(o, dict):
        return [s for v in o.values() for s in _flatten(v)]
    if isinstance(o, list):
        return [s for v in o for s in _flatten(v)]
    return []


def _norm(t: str) -> str:
    return re.sub(r"[^a-z0-9%.° /-]+", " ", re.sub(r"\s+", " ", t.lower())).strip()


def grounding(records: dict[str, dict]) -> dict:
    res = Counter()
    examples = []
    for name, run in records.items():
        case = case_for(name)
        prep = prep_for(case)
        payload = json.loads(prep.user_prompt.split("INPUT (JSON):\n", 1)[1])
        corpus_raw = " ".join(_flatten(payload)) + " " + json.dumps(payload, ensure_ascii=False)
        corpus = _norm(corpus_raw)
        tokens = set(re.findall(r"[a-z0-9.%°-]+", corpus))
        for a in ev._model_result(run)["assessments"]:
            for e in a.get("evidence", []):
                res["total"] += 1
                n = _norm(e)
                words = re.findall(r"[a-z0-9.%°-]+", n)
                nums = re.findall(r"\d+(?:\.\d+)?", n)
                num_ok = all(x in tokens or x in corpus for x in nums)
                if n and n in corpus:
                    res["exact"] += 1
                elif words and sum(w in tokens for w in words) / len(words) >= 0.8 and num_ok:
                    res["token_grounded"] += 1
                else:
                    res["ungrounded"] += 1
                    if len(examples) < 12:
                        examples.append(f"{name} {a['test_id']}: {e[:160]}")
                if not num_ok:
                    res["number_not_in_input"] += 1
    return {**res, "examples": examples}


# ---------------------------------------------------------------------------------------------------------------------
# consistency
# ---------------------------------------------------------------------------------------------------------------------


def _map_ids(pred: dict, kind: str) -> dict:
    if kind != "P4":
        return pred
    return {f"TV-{int(t.split(chr(45))[1]) - 40:03d}": v for t, v in pred.items()}


def consistency(app: dict[str, dict]) -> dict:
    out = {}
    for view in ("raw", "postcheck"):
        v = "raw" if view == "raw" else "post"
        rep = {}
        for sid in ar.REPEAT_SCENARIOS:
            runs = {n: r for n, r in app.items() if re.fullmatch(rf"{sid}_r\d+", n)}
            preds = {n: statuses(r, case_for(n), v) for n, r in runs.items()}
            if not preds:
                continue
            tests = sorted(next(iter(preds.values())))
            flips = {t: Counter(p[t]["status"] for p in preds.values() if t in p) for t in tests}
            unstable = {t: dict(c) for t, c in flips.items() if len(c) > 1}
            critical_flips = {
                t: dict(c)
                for t, c in unstable.items()
                if SC[sid]["tests"][t]["critical"] and not all(s in SC[sid]["tests"][t]["accept"] for s in c)
            }
            rep[sid] = {
                "runs": len(preds),
                "served_by": dict(Counter(runs[n]["served_by"] for n in runs)),
                "unstable_tests": unstable,
                "n_unstable": len(unstable),
                "tests": len(tests),
                "unstable_and_sometimes_wrong_critical": critical_flips,
            }
        pert = {}
        for sid in ar.REPEAT_SCENARIOS:
            base = app.get(f"{sid}_r1")
            if not base:
                continue
            bp = statuses(base, case_for(f"{sid}_r1"), v)
            for k in ("P1", "P2", "P3", "P4"):
                name = f"{k}_{sid}"
                if name not in app:
                    continue
                pp = _map_ids(statuses(app[name], case_for(name), v), k)
                changed = {
                    t: (bp[t]["status"], pp[t]["status"]) for t in bp if t in pp and bp[t]["status"] != pp[t]["status"]
                }
                bad = {
                    t: x
                    for t, x in changed.items()
                    if x[1] not in SC[sid]["tests"][t]["accept"] and SC[sid]["tests"][t]["critical"]
                }
                pert[name] = {
                    "served_by": app[name]["served_by"],
                    "base_served_by": base["served_by"],
                    "changed": changed,
                    "n_changed": len(changed),
                    "becomes_wrong_critical": bad,
                }
        out[view] = {"repeats": rep, "perturbations": pert}
    return out


# ---------------------------------------------------------------------------------------------------------------------
# reliability, calibration, nature
# ---------------------------------------------------------------------------------------------------------------------


def reliability(app_all: list[dict]) -> dict:
    ok = [r for r in app_all if r.get("ok")]
    bad = [r for r in app_all if not r.get("ok")]
    lat = defaultdict(list)
    for r in ok:
        lat[r["served_by"]].append(r["latency_s"])
    warn = Counter()
    for r in ok:
        for w in r["warnings"]:
            for key in (
                "returned no assessment",
                "unknown test ID",
                "twice",
                "non-changed requirement",
                "approval-like",
                "no interpretation",
                "invalid output",
                "provider rejected",
                "output truncated",
            ):
                if key in w:
                    warn[key] += 1

    def q(xs, p):
        xs = sorted(xs)
        return xs[min(len(xs) - 1, int(p * len(xs)))] if xs else None

    return {
        "cases": len(app_all),
        "answered": len(ok),
        "failed_after_retry": len(bad),
        "first_attempt_failed": sum(bool(r.get("first_attempt_failed")) for r in ok) + len(bad),
        "served_by": dict(Counter(r["served_by"] for r in ok)),
        "fallback_used": sum(r["fallback_used"] for r in ok),
        "valid_first_try": sum(
            r["attempts"] == 1 and not any("provider rejected" in w or "invalid output" in w for w in r["warnings"])
            for r in ok
        ),
        "attempts_gt1": sum(r["attempts"] > 1 for r in ok),
        "latency_s": {
            m: {"n": len(x), "median": statistics.median(x), "p90": q(x, 0.9), "max": max(x)} for m, x in lat.items()
        },
        "warning_counts": dict(warn),
        "approval_hits": sum(
            len(approval_language(a["reason"] + " " + a["recommended_action"]))
            for r in ok
            for a in r["result"]["assessments"]
        ),
        "errors": [redact_err(r.get("error", "")) for r in bad],
    }


def redact_err(t: str) -> str:
    return re.sub(r"org_[a-z0-9]+", "org_REDACTED", t)[:300]


def calibration(cs: list[dict]) -> dict:
    t = defaultdict(lambda: [0, 0])
    for c in cs:
        if c["confidence"]:
            t[c["confidence"]][0] += 1
            t[c["confidence"]][1] += c["ok"]
    return {k: {"n": v[0], "ok": v[1], "wrong": v[0] - v[1]} for k, v in t.items()}


def nature(app: dict[str, dict]) -> dict:
    labels = yaml.safe_load((ROOT / "eval" / "nature_labels.yaml").read_text())
    for sid, sc in SC.items():
        if sc.get("expect_nature"):
            labels[sid] = sc["expect_nature"]
    rows, total, right = [], 0, 0
    for name, run in app.items():
        case = case_for(name)
        if case["kind"] != "base" or case["scenario"] not in labels:
            continue
        got = {i["requirement_id"]: i for i in run["result"]["change_interpretations"]}
        for req, accepted in labels[case["scenario"]].items():
            i = got.get(req)
            total += 1
            ok = bool(i) and i["nature"] in accepted
            right += ok
            numbers = []
            if i:
                diff = prep_for(case).diff
                ch = next((c for c in diff.requirement_changes if c.req_id == req), None)
                numbers = [n.new_text for n in (ch.numeric_changes if ch else []) if n.new_text and n.unit]
            mentions = (
                all(re.search(re.escape(x.split()[0]), i["engineering_summary"]) for x in numbers)
                if (i and numbers)
                else None
            )
            rows.append(
                {
                    "scenario": case["scenario"],
                    "req": req,
                    "got": i["nature"] if i else None,
                    "accepted": accepted,
                    "ok": ok,
                    "served_by": run["served_by"] if "served_by" in run else "",
                    "summary_names_new_value": mentions,
                }
            )
    # stability across repeats
    stab = {}
    for sid, req in (("S1", "VCU-DR-01"), ("N4", "VCU-BRK-03")):
        vals = []
        for n, r in app.items():
            if re.fullmatch(rf"{sid}_r\d+", n):
                for i in r["result"]["change_interpretations"]:
                    if i["requirement_id"] == req:
                        vals.append(i["nature"])
        stab[f"{sid} {req}"] = dict(Counter(vals))
    return {"scored": total, "right": right, "rows": rows, "stability": stab}


# ---------------------------------------------------------------------------------------------------------------------


def main() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    data = {name: load(p) for name, p in SOURCES.items() if p.exists()}
    out: dict = {"accuracy": {}, "errors": {}, "calibration": {}}
    md: list[str] = ["# Phase 4 tables (generated by eval/assess_analyze.py)\n"]
    for view in ("raw", "postcheck"):
        v = "raw" if view == "raw" else "post"
        md.append(f"\n## Accuracy, {view} view (first run of each scenario)\n")
        md.append(
            "| Source | Set | Judgments (distinct) | Acceptable | Preferred | Critical ok (distinct critical) | Missed impacts | Over-flags |\n|---|---|---|---|---|---|---|---|"
        )
        for sname, recs in data.items():
            for dsname, flt in (
                ("S1-S10", lambda c: c["dataset"] == "S"),
                ("N1-N6 held out", lambda c: c["dataset"] == "N"),
                ("S8-S10 + N1-N6", lambda c: c["held_out"]),
            ):
                cs = [c for c in cells(recs, v) if flt(c)]
                if not cs:
                    continue
                s = summarize(cs)
                out["accuracy"].setdefault(view, {}).setdefault(sname, {})[dsname] = s
                md.append(
                    f"| {sname} | {dsname} | {s['judgments']} ({s['distinct_cells']}) | {rate(s['ok'], s['judgments'])} | "
                    f"{rate(s['strict'], s['judgments'])} | {rate(s['critical_ok'], s['critical'])} ({s['distinct_critical']}) | "
                    f"{s['missed']} | {s['over_flags']} |"
                )
        # error analysis for the application path
        app = data.get("app (Groq, Gemini fallback)", {})
        cs = cells(app, v)
        wrong = [c for c in cs if not c["ok"]]
        cat = Counter(category(c) for c in wrong)
        out["errors"][view] = {
            "by_category": dict(cat),
            "cells": [
                f"{c['scenario']} {c['test']}: got {c['got']} (accept {c['accept']}, critical={c['critical']}, served by {c['served_by']}, conf {c['confidence']})"
                for c in wrong
            ],
        }
        md.append(f"\n### Wrong cells of the application path, {view} view: {len(wrong)}\n")
        md += [f"- {x}" for x in out["errors"][view]["cells"]]
        md.append("\nBy category: " + ", ".join(f"{k} {n}" for k, n in cat.items()))
        # action / related constraints
        act = [(c, set(c["actions"])) for c in cs if c["label_actions"]]
        act_ok = sum(ev._check_constraint(c["label_actions"], a) for c, a in act)
        rel = [c for c in cs if c["label_related"]]
        rel_ok = sum(ev._check_constraint(c["label_related"], set(c["related"])) for c in rel)
        md.append(
            f"\nAction constraints met: {rate(act_ok, len(act))}; related-requirement constraints met: {rate(rel_ok, len(rel))}"
        )
        out["errors"][view]["actions"] = [act_ok, len(act)]
        out["errors"][view]["related"] = [rel_ok, len(rel)]
        cal = calibration(cs)
        out["calibration"][view] = cal
        md.append(
            f"\n### Confidence vs correctness (application path, {view} view)\n\n| Confidence | Cells | Acceptable | Wrong | Wrong rate |\n|---|---|---|---|---|"
        )
        for k in ("high", "medium", "low"):
            if k in cal:
                c = cal[k]
                md.append(f"| {k} | {c['n']} | {c['ok']} | {c['wrong']} | {rate(c['wrong'], c['n'])} |")
        cs_crit = [c for c in cs if c["critical"] and c["confidence"] == "high" and not c["ok"]]
        md.append(f"\nHigh-confidence wrong critical cells: {len(cs_crit)}")

    app = data.get("app (Groq, Gemini fallback)", {})
    if app:
        g = grounding(app)
        out["grounding"] = g
        md.append(f"\n## Evidence grounding (application path, all {len(app)} runs, against the model's input)\n")
        t = g.get("total", 0)
        md.append(
            f"Evidence strings: {t}; exact text found in input: {rate(g.get('exact', 0), t)}; token-grounded (>=80% of words and all numbers in input): {rate(g.get('token_grounded', 0), t)}; **not grounded: {rate(g.get('ungrounded', 0), t)}**; strings containing a number that is not in the input: {rate(g.get('number_not_in_input', 0), t)}."
        )
        md += [f"- {e}" for e in g["examples"]]
        c = consistency(app)
        out["consistency"] = c
        for view, cv in c.items():
            md.append(f"\n## Consistency, {view} view\n")
            for sid, r in cv["repeats"].items():
                md.append(
                    f"- {sid}: {r['runs']} repeats, served by {r['served_by']}; tests with more than one status: {r['n_unstable']}/{r['tests']} {r['unstable_tests']}; unstable AND sometimes outside the accepted set on a critical cell: {r['unstable_and_sometimes_wrong_critical'] or 'none'}"
                )
            for name, p in cv["perturbations"].items():
                md.append(
                    f"- {name} (served by {p['served_by']}; base by {p['base_served_by']}): {p['n_changed']} status changes {p['changed'] or ''}; critical cell becomes wrong: {p['becomes_wrong_critical'] or 'none'}"
                )
        recs = []
        for f in sorted(SOURCES["app (Groq, Gemini fallback)"].glob("*.json")):
            recs.append(json.loads(f.read_text()))
        out["reliability"] = reliability(recs)
        md.append(
            "\n## Reliability (application path)\n\n```json\n" + json.dumps(out["reliability"], indent=1) + "\n```"
        )
        n = nature(app)
        out["nature"] = {k: v for k, v in n.items() if k != "rows"}
        md.append(
            f"\n## Change interpretation (nature)\n\nScored requirement readings: {rate(n['right'], n['scored'])}. Stability over repeats: {n['stability']}\n"
        )
        for r in n["rows"]:
            md.append(
                f"- {r['scenario']} {r['req']}: got {r['got']} accepted {r['accepted']} {'ok' if r['ok'] else 'WRONG'}; summary names new value: {r['summary_names_new_value']}"
            )
        out["nature_rows"] = n["rows"]
    (OUTDIR / "phase4_results.json").write_text(json.dumps(out, indent=1, ensure_ascii=False, default=str))
    (OUTDIR / "phase4_tables.md").write_text("\n".join(md) + "\n")
    print("\n".join(md[:60]))


if __name__ == "__main__":
    main()
