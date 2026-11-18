# Demo script: three live changes

Run the app (`uv run streamlit run app/streamlit_app.py`, key in `.env`), open **3 · Edit and re-analyse**, apply the edit, check tab 1, click
**Run analysis with the LLM** in the sidebar, then look at tabs 2 and 4. "Actual" results are from real runs on 2026-11-18 through exactly these UI steps
(`eval/ui_flows.py`, files `docs/assessment/results/ui_flows_live_final_F*.json`). Model output varies from run to run: say "typically", not "always".

**Important to say first:** the revised file already contains the real change DR-01 100 -> 80 ms, so your edit is diffed against the *baseline*:
tab 1 always shows DR-01 as well as your change (a known limitation, F-004). With a live model, edits show up as "Live" or "Cached"; the recorded
"Replayed" result only exists for the provided files.

## Demo 1: change a numeric limit (DR-01 to 60 ms)

Edit VCU-DR-01: `within 80 milliseconds` -> `within 60 milliseconds`.
- **Expected:** tab 1 shows `100 milliseconds -> 60 milliseconds` (tightened). TV-001 (script at 100 ms, previous 94 ms) directly affected: re-run and update procedure; TV-003 (no link, 92 ms) directly or possibly affected; TV-004 (88 ms brake latency, different clock) **not affected**; TV-007 (80 % pedal) needs human review, not "80 ms".
- **Actual (Groq, 6.8 s):** TV-001 directly/high, TV-002 possibly/medium, TV-003 directly/medium, TV-007 needs review/low, all other tests not affected; interpretation "tightened".

## Demo 2: reword a requirement without changing the meaning (DR-02)

Edit VCU-DR-02: `shall ignore transient spikes shorter than 10 milliseconds` -> `shall disregard brief spikes that last less than 10 milliseconds`.
- **Expected:** DR-02 read as a rewording with the same meaning; TV-010 (7 ms spike injection) **not affected**. The DR-01 effects from the real revision remain.
- **Actual (Gemini fallback, the primary was rate-limited that minute; 4.4 s after a pause):** TV-010 not affected/high; TV-001, TV-002 and TV-003 directly affected (because of DR-01, not DR-02). The banner showed "groq ... per-minute rate limit of the free tier; wait a minute and run again" and the answer came from Gemini.
- **Watch for:** this is the failure mode the application knows about (a model may mark TV-010 directly affected while its own reason says "editorial"). If it happens, the test row shows the original and the corrected status ("changed by the application's post-check") - point to it and say it is a safety net, not a better model.

## Demo 3: add a new requirement

Add VCU-THM-07 "Thermal torque derating": `When the inverter temperature exceeds 85 °C, the controller shall limit positive torque to 50% of the demand.`, after VCU-MOD-06.
- **Expected:** tab 1 shows THM-07 as added (a green block, interpretation "added"); TV-007 "Acceleration at thermal load" (TBD link, NOT RUN) is the natural candidate: needs human review or possibly affected; TV-006 and TV-004 not affected.
- **Actual (Groq, 5.5 s):** TV-007 needs human review/low, TV-009 possibly/medium, TV-002 and TV-003 possibly/medium, TV-001 directly/high (DR-01), the rest not affected.

## If the live provider is slow or limited

- The free tiers allow about one analysis per minute on Groq and about 30 per day; a second click inside a minute usually falls back to Gemini (40-65 s) or fails.
  The banner then says why ("daily token limit ... reached", "per-minute rate limit ...") and keeps the diff and register facts.
- Say so openly and **switch to what needs no model**: the provided files in replay mode (tab 2 and the report), the committed example report
  `reports/example_impact_report.html`, and any scenario file under `eval/scenarios/` uploaded as the revised spec (recorded for S1-S7).
- Run each demo change once **before** the interview: the result is cached in `.cache/` and shown again as "From an earlier live run" (also after a browser refresh) without calling the provider.
- Do not click twice while it is running. If a run seems stuck: the app gives up on one provider after 240 s.
