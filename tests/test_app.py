"""Headless smoke tests of the Streamlit app (replay mode, no model configured)."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from vcu_impact import cache

APP = str(Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py")


@pytest.fixture(autouse=True)
def no_model(monkeypatch, tmp_path):
    # load_dotenv does not override variables that are already set, so empty values
    # keep any local .env from enabling a live model during tests.
    for var in ("LLM_PROVIDER", "LLM_FALLBACK_PROVIDER"):
        monkeypatch.setenv(var, "")
    monkeypatch.setattr(cache, "LOCAL_CACHE_DIR", tmp_path / "cache")


def _run() -> AppTest:
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    return at


def test_app_loads_default_inputs_in_replay_mode():
    at = _run()
    assert any("Replayed" in i.value for i in at.info)
    assert [t.label for t in at.tabs] == ["1 · What changed", "2 · Affected tests"]
    df = at.dataframe[0].value
    assert len(df) == 12
    assert df.loc[df["Test"] == "TV-001", "Status"].item().endswith("Directly affected")
    assert df.loc[df["Test"] == "TV-004", "Status"].item().endswith("Not affected")


def test_run_button_disabled_without_model():
    at = _run()
    assert at.sidebar.button[0].disabled
