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
    assert [t.label for t in at.tabs] == [
        "1 · What changed",
        "2 · Affected tests",
        "3 · Edit and re-analyse",
        "4 · Report",
    ]
    df = at.dataframe[0].value
    assert len(df) == 12
    assert df.loc[df["Test"] == "TV-001", "Status"].item().endswith("Directly affected")
    assert df.loc[df["Test"] == "TV-004", "Status"].item().endswith("Not affected")


def test_run_button_disabled_without_model():
    at = _run()
    run_button = next(b for b in at.sidebar.button if "analysis with the LLM" in b.label)
    assert run_button.disabled


def _button(at: AppTest, label: str):
    return next(b for b in at.button if b.label == label)


def test_edit_updates_diff_and_marks_result_not_analysed():
    at = _run()
    area = at.text_area[0]  # "Edit a requirement" form, first requirement (VCU-DR-01)
    assert "within 80 milliseconds" in area.value
    area.set_value(area.value.replace("within 80 milliseconds", "within 90 milliseconds"))
    _button(at, "Apply edit").click()
    at.run()
    assert not at.exception, at.exception
    page = " ".join(m.value for m in at.markdown)
    assert "<ins>90</ins>" in page  # word-level diff against the baseline shows the new value
    assert any("Not analysed" in w.value and "no recorded analysis" in w.value for w in at.warning)
    assert any("1 edit(s) applied" in m.value for m in at.sidebar.markdown)

    _button(at, "Undo last edit").click()
    at.run()
    assert any("Replayed" in i.value for i in at.info)  # back to the recorded analysis


def test_adding_a_requirement_with_a_bad_id_is_rejected():
    at = _run()
    at.radio[0].set_value("Add a requirement").run()
    at.text_input[0].set_value("thermal")
    at.text_area[0].set_value("Some text.")
    _button(at, "Add requirement").click()
    at.run()
    assert any("Use an ID like" in e.value for e in at.error)
