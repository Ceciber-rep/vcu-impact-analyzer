# VCU-42 Spec Change Impact Analyzer

> Work in progress. This README will be completed once the application is built.

AI-assisted impact analysis for a fictional vehicle controller (VCU-42): compare two
specification revisions, find the existing tests that may be affected, review the LLM's
explanation, and export an engineering impact summary.

## Repository layout

| Path | Content |
| --- | --- |
| `data/input/` | Provided exercise inputs (baseline spec, revised spec, test register) |
| `docs/exercise_brief.docx` | Original exercise brief |
| `.env.example` | Template for LLM configuration (never commit a real `.env`) |
