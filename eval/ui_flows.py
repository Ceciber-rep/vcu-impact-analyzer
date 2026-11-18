"""Scripted end-to-end UI flows (Streamlit AppTest), re-runnable in replay or live mode.

    uv run python eval/ui_flows.py --mode replay              # no key, no model call
    uv run python eval/ui_flows.py --mode live --flows F1,F3  # calls the configured model (uses the local cache)

Each flow starts from a fresh app session, makes one change the way a user would (edit form
or file upload), optionally clicks "Run analysis", and records what the UI shows: banner,
changes, status per test, warnings, and the exported report (the HTML preview of the report tab,
which is the same string as the download). Results are written to --out (default
docs/assessment/results/ui_flows_<mode>.json). Nothing under eval/results is touched.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = str(ROOT / "app" / "streamlit_app.py")
INPUT = ROOT / "data" / "input"


def _spec_variant(edit) -> bytes:
    from vcu_impact import spec_editor as se

    doc = se.load((INPUT / "VCU_Spec_Revised.docx").read_bytes())
    edit(doc, se)
    return se.to_bytes(doc)


def _register_variant() -> bytes:
    import openpyxl

    wb = openpyxl.load_workbook(INPUT / "VCU_Test_Register.xlsx")
    ws = wb["Test register"]
    for row in ws.iter_rows(min_row=6):
        if row[0].value == "TV-003":  # a test without a link gets a link to VCU-DR-01
            row[3].value = "VCU-DR-01"
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _edit_form(at, req_id: str, old: str, new: str) -> None:
    at.selectbox(key="edit_req").set_value(req_id).run()
    area = at.text_area[0]
    assert old in area.value, f"{old!r} not in {area.value!r}"
    area.set_value(area.value.replace(old, new))
    _click(at, "Apply edit")


def _click(at, label: str) -> None:
    next(b for b in at.button if b.label == label).click()
    at.run()


def flow_f1(at):  # change a numeric limit
    _edit_form(at, "VCU-DR-01", "within 80 milliseconds", "within 60 milliseconds")


def flow_f2(at):  # reword without changing the meaning
    _edit_form(
        at,
        "VCU-DR-02",
        "shall ignore transient spikes shorter than 10 milliseconds",
        "shall disregard brief spikes that last less than 10 milliseconds",
    )


def flow_f3(at):  # add a requirement
    at.radio(key="edit_mode").set_value("Add a requirement").run()
    at.text_input[0].set_value("VCU-THM-07")
    at.text_input[1].set_value("Thermal torque derating")
    at.text_area[0].set_value(
        "When the inverter temperature exceeds 85 °C, the controller shall limit positive torque to 50% of the demand."
    )
    _click(at, "Add requirement")


def flow_f4(at):  # remove a requirement
    at.radio(key="edit_mode").set_value("Remove a requirement").run()
    at.selectbox[0].set_value("VCU-LOG-05")
    _click(at, "Remove requirement")


def flow_f5(at):  # change a trigger condition (no number involved)
    _edit_form(at, "VCU-DGN-04", "If the wheel-speed input is unavailable", "If the wheel-speed input is unavailable "
               "and the vehicle is moving")


def flow_f6(at):  # upload a modified spec
    def edit(doc, se):
        se.replace_in_requirement(doc, "VCU-BRK-03", "regardless of pedal position or requested driving mode", "regardless of pedal position")

    at.sidebar.expander[0]  # the uploader lives in the sidebar expander
    at.file_uploader(key="up_revised").set_value(("VCU_Spec_Revised_modified.docx", _spec_variant(edit), "application/octet-stream")).run()


def flow_f7(at):  # upload a modified register
    at.file_uploader(key="up_register").set_value(("VCU_Test_Register_modified.xlsx", _register_variant(), "application/octet-stream")).run()


FLOWS = {
    "F1": ("Change a numeric limit (DR-01 80 -> 60 ms)", flow_f1, True),
    "F2": ("Reword a requirement, same meaning (DR-02)", flow_f2, True),
    "F3": ("Add a requirement (VCU-THM-07)", flow_f3, True),
    "F4": ("Remove a requirement (VCU-LOG-05)", flow_f4, True),
    "F5": ("Change a trigger condition (DGN-04 adds 'and the vehicle is moving')", flow_f5, True),
    "F6": ("Upload a modified spec (BRK-03 loses a clause)", flow_f6, True),
    "F7": ("Upload a modified register (TV-003 linked to DR-01)", flow_f7, True),
    "F0": ("Provided files, nothing changed", lambda at: None, False),
}


def snapshot(at) -> dict:
    """What the user sees after the flow."""
    from vcu_impact.analysis import approval_language

    page = " ".join(m.value for m in at.markdown)
    table = at.dataframe[0].value if len(at.dataframe) else None
    statuses = {}
    if table is not None:
        statuses = {r["Test"]: [r["Status"], r["Confidence"], r["Required actions"]] for _, r in table.iterrows()}
    iframe = at.get("iframe")
    report = iframe[0].proto.srcdoc if iframe else ""
    banner = [x.value for x in [*at.info, *at.success, *at.warning, *at.error]]
    changes = re.findall(r"\*\*(VCU-[A-Z0-9-]+) · [^*]*\*\* &nbsp; (\S+ \w+)", page)
    return {
        "exceptions": [str(e.value) for e in at.exception],
        "banner": banner[:6],
        "changes_shown": changes,
        "statuses": statuses,
        "report_chars": len(report),
        "report_contains_every_test": all(t in report for t in statuses),
        "report_contains_every_status_label": all(re.sub(r"^\S+ ", "", s[0]) in report for s in statuses.values()),
        "approval_hits_in_report": approval_language(re.sub(r"<[^>]+>", " ", report)),
    }


def run_flow(name: str, mode: str) -> dict:
    from streamlit.testing.v1 import AppTest

    if mode == "replay":
        os.environ["LLM_PROVIDER"] = ""
        os.environ["LLM_FALLBACK_PROVIDER"] = ""
    title, fn, edits = FLOWS[name]
    at = AppTest.from_file(APP, default_timeout=900)
    at.run()
    t0 = time.time()
    fn(at)
    after_change = snapshot(at)
    out = {"flow": name, "title": title, "mode": mode, "after_change": after_change}
    if mode == "live" and edits:
        run_btn = next(b for b in at.sidebar.button if "analysis with the LLM" in b.label)
        if run_btn.disabled:
            out["live_run"] = "button disabled"
        else:
            run_btn.click()
            at.run()
            out["after_analysis"] = snapshot(at)
    out["seconds"] = round(time.time() - t0, 1)
    return out


def main() -> None:
    sys.path.insert(0, str(ROOT / "src"))
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["replay", "live"], default="replay")
    p.add_argument("--flows", default=",".join(FLOWS))
    p.add_argument("--out")
    args = p.parse_args()
    results = []
    for name in args.flows.split(","):
        print(f"{name}: {FLOWS[name][0]} ...", flush=True)
        try:
            results.append(run_flow(name, args.mode))
        except Exception as exc:  # noqa: BLE001 - record the failure, keep going
            results.append({"flow": name, "mode": args.mode, "error": f"{type(exc).__name__}: {exc}"})
    out = Path(args.out or ROOT / "docs" / "assessment" / "results" / f"ui_flows_{args.mode}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    # Provider error messages contain an organisation id: redact it before writing anything to disk.
    out.write_text(re.sub(r"org_[a-z0-9]+", "org_REDACTED", json.dumps(results, indent=1, ensure_ascii=False)))
    print("wrote", out)


if __name__ == "__main__":
    main()
