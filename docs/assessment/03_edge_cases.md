# Phase 3: edge cases and robustness

Tests: `tests/test_robustness_inputs.py` (inputs, E-001..E-032), `tests/test_robustness_llm_ui.py` (LLM layer, exports, UI, E-040..E-072),
builders in `tests/builders.py`. Live probe: `eval/injection_probe.py` (results `results/injection.json`). Run: `uv run pytest`.
Current result: **99 passed, 32 xfailed** (each xfail is `strict`: a documented defect that will turn the suite red when fixed, so the marker must then be removed).
Everything is offline and deterministic except the injection probe (3 live calls). The synthetic Word files are built with python-docx plus hand-written
OOXML (tracked changes, text box); they were **not saved by Word**, and the "password-protected" file is only an OLE header (not verified with a real encrypted file).

## Results by area

| Area | Tests | Result |
|---|---|---|
| Identical specs, same file twice, swapped baseline/revised, ID added/removed/renamed, duplicate IDs, empty body, 400 requirements, 300 kB text | E-001..E-007, E-020 | Pass. Identical: clear "nothing to assess" state. Duplicate ID: error names the ID. A 300 kB requirement builds a >300 kB prompt with no guard (provider will reject; visible failure) |
| Unusual ID formats | E-008, E-009 | **Fail (F-012)**: `SYS_001`, `vcu-a-01`, `VCU-A-01a`, `R1` headings are not recognised and their text is silently appended to the previous requirement; `VCU-A-01.2` becomes ID `VCU-A-01`, title "2 ..." |
| Numbers and units | E-010..E-013 | Pass: `100 ms`=`100 milliseconds`, decimal comma, percent word, changed percentage and range. **Fail (F-001)**: `100 ms` vs `0.1 s`/`0.10 seconds`; number inside a referenced ID |
| Word features | E-014..E-017 | **Fail (F-010, S1)**: text inside tracked changes is ignored: a revised requirement with `<w:del>100 ms</w:del><w:ins>80 ms</w:ins>` parses as "The value is" (both numbers vanish; the diff shows only a deletion). **Fail (F-011)**: requirements in text boxes or tables are dropped without a warning. Pass: header text not read as a requirement; a changed non-requirement section appears in `section_changes` |
| Bad files | E-018, E-018b, E-019, E-031 | **Fail (F-013)**: empty / corrupt / old `.doc` / encrypted give "File is not a zip file" or "File contains no valid workbook part". Pass: xlsx uploaded as spec says "not a Word file" (with an ugly `<_io.BytesIO ...>` repr). The UI shows this text verbatim after "was not loaded" and never crashes |
| Register shapes | E-021..E-024, E-030 | Pass: 0 tests (clear error), 1 test, blank rows, other column order and header wording, extra columns. 200 tests build a ~100 k character prompt (estimated 30 k+ input tokens and ~30 k output tokens; **live run not verified**; the UI warns above 60 tests; Groq free-tier limits make failure likely and it would be a visible provider error) |
| Register content | E-025..E-029 | **Fail (F-014)**: merged-cell text and formulas without cached values become empty strings, no warning. **Fail (F-015)**: duplicate test IDs accepted. **Fail (F-016)**: `VCU-A-01\nVCU-B-02` and `VCU-A-01 VCU-B-02` keep only the first ID. **Fail (F-017)**: `vcu-a-01` is "unknown requirement". Pass: `;` `,` separators, trailing text, `N/A` (TBD), `see notes` (unknown) |
| Provider failures | E-040..E-046 | Pass for 401, 429, 413, timeout, 503, connection error, "no valid output": each gives `not_analysed` with the error class in the reason, nothing cached, no invented assessments; fallback used and primary failure recorded; empty answer / truncation / invalid JSON end in a clear `LLMError` after at most one repair; provider schema rejection goes through repair. UI shows the warning (E-070) |
| Model output integrity | E-047..E-049 | Pass: omitted tests become `needs_human_review` plus a warning each; invented and duplicate test IDs dropped with warnings; invented requirement IDs removed from `related_requirements` |
| Prompt injection | E-050, E-051, probe | Injected text stays inside JSON strings (E-050). Live probe, 3 cases, primary model, n=1 each: register-cell instruction, requirement-text instruction, both: **the model was not steered** (TV-001 stayed directly affected in all three; not every test became not_affected; no approval wording; `obeyed=false`). This is 3 samples of one model, not proof of resistance |
| Approval detector | E-051, E-052 | Pass on plain claims and negations. **Fail (F-005)**: 5 phrasings missed (`owner approved`, `approval is granted`, `cleared for release`, `accepted`, `authorised`) |
| Cache and reproducibility | E-053, E-054b, E-072 | Pass: a cache hit makes 0 provider calls; reports are identical apart from the "generated ... UTC" stamp (F-019, S4). **Fail (F-020, S2)**: see below |
| Export and XSS | E-060..E-064 | Pass: `<script>`, `<img onerror>` in requirement title/text, test name/comment/procedure and model reason/evidence/summary are escaped in the HTML report and in every `unsafe_allow_html` element of the UI; non-ASCII (Ω, °C, CJK, emoji) round-trips; reports for no changes, a failed analysis and 39 changes contain every test. **Fail (F-018)**: Markdown syntax in untrusted text (images, links) is rendered by the UI |
| UI flows | E-070, E-071 | Pass: failed run shows a warning banner; edit then revert returns to the original result (same key) |

## Not verified

- Double-click / click during a long run / browser refresh *during* a run: AppTest cannot interrupt a blocking call. From the code: a second click while a call is in flight starts a second provider call (`analyze(mode="live")` does not look at the cache), so duplicate spend is plausible (F-021, S3, not verified).
- Real browser rendering of hostile text (checked only as HTML strings and AppTest elements); real Word-saved tracked-change files; real password protection; a live 200-test run; live-vs-replay comparison of the demo flows beyond `results/ui_flows_*.json`.

## New findings (continuing the numbering of phase 1)

| ID | Sev | Finding |
|---|---|---|
| F-010 | **S1** | Tracked changes in a Word spec are ignored silently. A revision saved with tracked changes (common in Word workflows) loses both the deleted and the inserted text, so a real limit change can be missing or shown as a bare deletion, with no warning. Evidence: E-014, E-015 |
| F-011 | S2 | Requirements inside text boxes or tables are not parsed; no warning |
| F-012 | S2 | Headings with an unrecognised ID format are merged into the previous requirement; `VCU-A-01.2` is truncated |
| F-013 | S3 | Raw library messages for corrupt, empty, old-format, encrypted or wrong-type files |
| F-014 | S3 | Merged cells and uncached formulas in the register become empty values silently |
| F-015 | S2 | Duplicate test IDs in the register are accepted silently (their assessments collide) |
| F-016 | S2 | A link cell with several IDs separated by newline or space keeps only the first (the later links are lost, so `fix_link` and validity are wrong) |
| F-017 | S3 | Lower-case requirement IDs in link cells are "unknown requirement" |
| F-018 | S3 | Markdown in untrusted text (register cells, model reasons) is rendered: a remote image could be fetched when the page is shown |
| F-019 | S4 | Exported reports carry a generation timestamp, so they are not byte-identical (identical apart from it) |
| F-020 | **S2** | After a browser refresh the earlier live result is not shown: `st.cache_data` in `streamlit_app._replay` keeps the "not analysed" outcome per input key for the whole server process, although the live result is on disk. The user sees "not analysed" and the button says "Run", so a click calls the provider again (wasted quota). Evidence: E-072 |
| F-021 | S3 | Concurrent clicks may start duplicate provider calls (not verified) |

Also confirmed again: F-001 (E-011, E-013), F-005 (E-051).

Counts so far (phases 1 and 3, 21 findings): S1 1 (F-010), S2 8 (F-001, F-002, F-007, F-011, F-012, F-015, F-016, F-020; F-007 is a contested model reading), S3 9, S4 3.
