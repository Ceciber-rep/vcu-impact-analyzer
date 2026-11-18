# Decision rule outcome

Prompt version v3; post-check applied; original + held-out cells (32 critical cells).

Rule: the primary model stays unless a challenger has strictly fewer critical failures AND zero missed impacts. Ties go to the primary. A scenario without a valid run counts all its critical cells as failures.

| Model | Critical failures | Missed impacts | Missing scenarios | Replaces the primary? |
|---|---|---|---|---|
| gemini-3.5-flash | 1 | 0 | - | no: not strictly fewer critical failures |
| groq-gpt-oss-120b | 4 | 3 | - | no: not strictly fewer critical failures; 3 missed impact(s) |
| groq-qwen3.8-27b | 1 | 0 | - | (primary) |

Cells behind the numbers:

- **gemini-3.5-flash** critical failures: S8 TV-002: got D, expected N/P
  - missed impacts: none
- **groq-gpt-oss-120b** critical failures: S1 TV-007: got N, expected P/R; S8 TV-001: got N, expected D/P; S10 TV-007: got N, expected P/R; S10 TV-013: got D, expected N/P
  - missed impacts: S1 TV-007, S8 TV-001, S10 TV-007
- **groq-qwen3.8-27b** critical failures: S8 TV-002: got D, expected N/P
  - missed impacts: none

**Outcome: groq-qwen3.8-27b stays primary.**
