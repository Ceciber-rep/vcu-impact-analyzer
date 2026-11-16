"""Smoke test: one tiny structured-output call per candidate model.

    uv run python eval/smoke.py github:openai/gpt-4.1 gemini:gemini-2.5-flash ...

Checks credentials, model availability and JSON-schema support before the
full evaluation spends any rate-limit budget.
"""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict

from vcu_impact.llm import LLMClient, LLMConfig


class Probe(BaseModel):
    model_config = ConfigDict(extra="forbid")
    old_limit_ms: int
    new_limit_ms: int
    measured_ms: int
    still_passes: bool


SYSTEM = "You extract facts and return JSON only."
USER = "A requirement limit changed from 100 ms to 80 ms. A previous test measured 94 ms. Does it still pass?"


def main(targets: list[str]) -> None:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    for target in targets:
        provider, model = target.split(":", 1)
        try:
            config = LLMConfig.from_env(provider=provider, model=model)
            config.timeout_s, config.max_retries = 90, 0
            client = LLMClient(config)
            res = client.structured(SYSTEM, USER, Probe)
            p = res.parsed
            verdict = (
                "correct"
                if (p.old_limit_ms, p.new_limit_ms, p.measured_ms, p.still_passes) == (100, 80, 94, False)
                else "WRONG"
            )
            print(f"OK   {target:45s} {res.latency_s:6.1f}s mode={res.structured_mode} answer={verdict} {res.notes}")
        except Exception as exc:  # noqa: BLE001 - diagnostic script
            print(f"FAIL {target:45s} {type(exc).__name__}: {str(exc)[:220]}")


if __name__ == "__main__":
    main(sys.argv[1:])
