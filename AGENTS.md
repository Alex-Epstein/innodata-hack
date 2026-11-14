# Innodata Hackathon · Visual Task Factory · rules for every agent (Claude, Codex, Cursor, Copilot, Gemini)

**First time here?** Do `docs/SETUP.md` ("Agent steps") before anything else.
**Every session and before every task:** run `scripts/catchup` (Claude Code runs it for you).

## Roles
- **Alex Epstein (`Alex-Epstein`) is the team lead.** Alex and his agent plan the work, create and assign issues,
  send directives, decide, and own the lead files: `AGENTS.md`, `docs/`, `contracts/`, `scripts/`, `.claude/`, `.github/`.
- **Everyone else (`tech-cosmos`, `dl3832`, `WindHurtLZ`) takes tickets.** If your user isn't Alex, you only work on
  an issue assigned to your user, inside that issue's folder. You never re-plan the project or edit lead files. Want
  something changed? Open an issue labeled `request` that mentions `@Alex-Epstein`.
- Not sure who your user is? `gh api user --jq .login`. If in doubt, act as a ticket-taker.

## What we're building
A pipeline that renders realistic images from structured data, asks a question that needs real reasoning, computes
the answer from the same data in code, checks every task automatically, and evaluates `anthropic/claude-haiku-5.5`
and `openai/gpt-6-luna` on them. **ZIP uploaded by 3:10 PM (hard deadline 3:30).** 5-minute presentation at 3:30.

**Golden path (must always work on `main`):** `generate --seed N` → data JSON + PNG + question + answer →
`validate` (all checks pass) → `eval` (both models answer, scored) → `results/` row. One command, also in Docker.
`scripts/check` runs it; run it before every merge.

**Know the project inside out: read `docs/OVERVIEW.md` first.** The pitch script is `docs/SCRIPT.md`.

## The files (and nothing else to read unless an issue points you there)
| File | What it is |
|---|---|
| `docs/OVERVIEW.md` | **The whole project from zero**: story, map lesson, missions, results, the 7 checks, Docker, Q&A |
| `docs/SCRIPT.md` | The 5-minute presentation script and who says what |
| `docs/BRIEFING.md` | **Now**: current plan, the order to claim issues in, next gate |
| `docs/DESIGN.md` | Art direction "Field Survey": type, colour meanings, 3D look. Every visual follows it |
| `docs/DEMO.md` | The 5-minute demo, second by second. We build exactly this |
| `docs/BRIEF.md` | The organizers' requirements and rubric (they win over anything else) |
| `contracts/SCHEMA.md` | Folder layout and file formats everyone builds against |
| `docs/ARCHITECTURE.md` | How the pipeline works; decisions D1 to D9 under discussion (issue #9) |
| `docs/DECISIONS.md` | One line per decision. Once written, don't re-argue it |
| `docs/IDEATION.md` | The idea shortlist (until the idea is picked) |
| `docs/EVIDENCE.md` | The only source for numbers in the README and slides |
| `NOTES.md` | Insights, limitations, weird model behavior: anyone appends |
| `docs/context/` | Background: kickoff talk, past wins, earlier plans. Index in its README |
| `docs/organizer/`, `tools/track2-format-check/` | Organizer files and their format checker |

## Think like the lead (use this for every judgment call)
You are an extension of Alex. When the issue doesn't say, decide the way he would:
- **We play to win the rubric** (`docs/BRIEF.md`): realism 20, reliable pipeline 20, fair 15, difficulty 15,
  variation 10, eval 10, runnable 10. Tie-break is validity. Spend effort where those points are.
- **Depth over breadth.** A few things done so well they can't be argued with beat many shaky ones.
- **Proof over claims.** Every answer is computed and double-checked by code; every number comes from a real run.
  Say where it fails, out loud.
- **Questions chain reasoning** (mentor's advice): read several facts from the image → apply a textbook rule →
  combine → one exact conclusion, in 3 to 5 steps. Single reads ("what's the value", "count these") are too easy. See #29.
- **Real material.** Images look like real software or publications, with real names and units, and a cited reference.
- **The demo is the product.** Judges answer our example task, then see the models miss it; a judge picks a seed
  and we build, check and score a fresh task live.
- Background on why (past wins, kickoff talk, earlier plans): `docs/context/README.md`. Read `KICKOFF.md` there once.

## How we work
1. **One issue = one person + agent.** Owner = the issue's assignee. Folder and "Done when" are in the issue.
2. **Directives first.** Issues labeled `directive` are agreed team tasks from the lead. If one names your user or
   "everyone": comment `ack`, do it before anything else, close it when done.
3. **Live log (issue #1).** After every meaningful step (started, finished, stuck, learned):
   `LOG_WHO="<name>'s agent" scripts/log "<what happened> (#issue)"`. Silence is the only wrong amount.
4. **Branch** `<area>/<topic>` from `main` → small commits **inside your folder** → PR using the template, with
   one new line in `status/<HHMM>-<name>-<slug>.md` (done / next / blocked) → squash-merge your own PR once the
   issue's "Done when" is met and `scripts/check` passes. `main` must always run.
5. **Blocked for more than 10 minutes** or need another folder changed: comment on the issue, add the `blocked` or
   `request` label, log it. Never work around it in someone else's folder.
6. **Done with your issue:** close it, log it, then take the next one per `docs/BRIEFING.md` (setup step 6).

## Rules that never bend
1. **Ground truth:** structured data first; the image is rendered from it by code; the answer is computed from it
   by code. Never an AI-generated image, never an answer from a model or a person reading the image.
2. **Model calls only through `eval/`'s client** (disk cache, retries, temperature 0, reasoning effort high, fixed
   max_tokens). Organizer keys only: $100 OpenRouter + $100 Anthropic for the **whole team**. **Budget caps are in
   `docs/BRIEFING.md`.** Before any batch: run `scripts/budget`, log the call count and estimated cost; after it, log
   the actual spend. Over $2 for one batch needs Alex's OK first.
3. **Keys** live only in `.env` (gitignored). Never print, log, commit or paste them anywhere.
4. **Contracts:** `contracts/SCHEMA.md` changes only via the lead, with a line in `docs/DECISIONS.md`.
5. **Numbers** in the README or slides come from `results/` via `docs/EVIDENCE.md`. Never round, never retype.
6. **Honesty:** report every result, disclose reused code and any manual step, and log limitations in `NOTES.md`.
7. **Explain as you go:** build in small pieces your user can follow, and tell them what you wrote and why.
