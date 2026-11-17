"""Turn evaluation runs into committed replay recordings for the application.

    uv run python eval/make_replay.py [--model groq-qwen3.8-27b] [--version v3]

For every scenario, the application's own pipeline computes the cache key from the
same inputs (baseline spec, scenario spec, original register), and the recorded run is
stored under data/replay/. The app then shows this real LLM output, labelled as
replayed, without needing an API key.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from vcu_impact import cache
from vcu_impact.analysis import AnalysisRun
from vcu_impact.pipeline import InputFile, Inputs, prepare
from vcu_impact.prompt import PROMPT_VERSION

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))
from evaluate import INPUT, load_dataset, scenario_path  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="groq-qwen3.8-27b")
    p.add_argument("--version", default=PROMPT_VERSION)
    args = p.parse_args()
    if args.version != PROMPT_VERSION:
        sys.exit(f"Recordings must match the current prompt ({PROMPT_VERSION}); got {args.version}.")

    for sc in load_dataset()["scenarios"]:
        run_file = ROOT / "eval" / "results" / args.version / args.model / f"{sc['id']}_r1.json"
        data = json.loads(run_file.read_text())
        if not data.get("ok"):
            print(f"{sc['id']}: skipped (run failed)")
            continue
        data.pop("ok")
        run = AnalysisRun.model_validate(data)
        inputs = Inputs(
            baseline=InputFile.from_path(INPUT / "VCU_Spec_Baseline.docx"),
            revised=InputFile.from_path(scenario_path(sc)),
            register=InputFile.from_path(INPUT / "VCU_Test_Register.xlsx"),
        )
        prep = prepare(inputs)
        entry = cache.CacheEntry(
            key=prep.key,
            prompt_version=run.prompt_version,
            label=f"evaluation scenario {sc['id']}: {sc['title']}",
            run=run,
        )
        path = cache.save(entry, cache.REPLAY_DIR)
        print(f"{sc['id']}: {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
