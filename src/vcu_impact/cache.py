"""Recorded LLM analyses, keyed by the exact LLM input.

Two locations are searched:
- ``data/replay/``: recordings committed to the repository, so the app shows real
  LLM output without credentials;
- ``.cache/analyses/`` (git-ignored): live runs made in this environment, so the same
  inputs are not sent to the provider twice.
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from vcu_impact.analysis import AnalysisRun
from vcu_impact.prompt import PROMPT_VERSION, SYSTEM_PROMPT

_REPO = Path(__file__).resolve().parents[2]
REPLAY_DIR = Path(os.getenv("VCU_REPLAY_DIR") or _REPO / "data" / "replay")
LOCAL_CACHE_DIR = Path(os.getenv("VCU_CACHE_DIR") or _REPO / ".cache" / "analyses")

Source = Literal["recorded", "local_cache"]


class CacheEntry(BaseModel):
    key: str
    prompt_version: str
    label: str = ""  # human description, e.g. "Evaluation scenario S1"
    run: AnalysisRun


def analysis_key(user_prompt: str) -> str:
    """Hash of everything the model sees: prompt version, system prompt, input."""
    h = hashlib.sha256()
    for part in (PROMPT_VERSION, SYSTEM_PROMPT, user_prompt):
        h.update(part.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def _filename(key: str, model_label: str) -> str:
    return f"{key[:16]}_{re.sub(r'[^A-Za-z0-9_.-]+', '_', model_label)}.json"


def find(key: str) -> tuple[CacheEntry, Source] | None:
    """Return the newest entry for ``key``; committed recordings take precedence."""
    for directory, source in ((REPLAY_DIR, "recorded"), (LOCAL_CACHE_DIR, "local_cache")):
        if not directory.exists():
            continue
        matches = []
        for path in directory.glob(f"{key[:16]}_*.json"):
            entry = CacheEntry.model_validate_json(path.read_text(encoding="utf-8"))
            if entry.key == key:
                matches.append(entry)
        if matches:
            return max(matches, key=lambda e: e.run.created_at), source
    return None


def save(entry: CacheEntry, directory: Path | None = None) -> Path:
    """Store an entry; by default in the local (git-ignored) cache."""
    directory = directory or LOCAL_CACHE_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / _filename(entry.key, entry.run.model_label)
    path.write_text(entry.model_dump_json(indent=1), encoding="utf-8")
    return path
