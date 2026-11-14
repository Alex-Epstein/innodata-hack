# Innodata Hackathon, Visual Task Factory: read before doing anything (every agent: Claude, Codex, Cursor, Copilot, Gemini)

**What we're building:** a pipeline that renders realistic images from structured data, asks a question that needs
real reasoning, computes the answer from the same data in code, checks every task automatically, and evaluates
`anthropic/claude-haiku-5.5` and `openai/gpt-6-luna` on them. The idea (which image family) is being picked now:
`docs/IDEATION.md`. Once picked, it's one line in `docs/DECISIONS.md` and the spec goes in `docs/SPEC.md`.

**Deadline: upload the ZIP by 3:30 PM ET (we aim for 3:10).** 5-minute presentation at 3:30.
The organizers' requirements, in short: `docs/BRIEF.md`. File formats we all build against: `contracts/SCHEMA.md`.

**Golden path** (must always work on `main`):
`generate --seed N` → data JSON + PNG + question + answer → `validate` (all checks pass) → `eval` (both models
answer, scored) → `results/` row. One command, also inside Docker.

## Team and ownership (fill in once roles are set)

| Person | GitHub | Owns (only their agents edit these paths) |
|---|---|---|
| Alex | Alex-Epstein | `validate/`, `contracts/`, `AGENTS.md`, `docs/DECISIONS.md` |
| | tech-cosmos | |
| | dl3832 | |
| | WindHurtLZ | |
| | | |

Suggested split: `validate/` + contracts · `eval/` · one generator family each under `gen/<family>/` ·
Dockerfile + README + format checker + slides.

## Rules for every person and every agent

1. **Start:** run `scripts/catchup`, read this file, `docs/DECISIONS.md` and the newest files in `status/`.
2. **Stay in your folder.** Need a change elsewhere? Ask its owner in the team chat or open an issue. Two agents never edit the same files.
3. **Contracts first.** `contracts/SCHEMA.md` is the shared format. Change it only with a line in `docs/DECISIONS.md` and a heads-up in the chat.
4. **Ground truth rule (organizers' hard rule):** structured data first, image rendered from it by code, answer computed from it by code. Never an AI-generated image, never an answer from a model or a person reading the image.
5. **Model calls only through `eval/`'s client.** It caches every response to disk (reruns are free), retries 429/5xx with backoff, and uses temperature 0, reasoning effort high, a fixed max_tokens. Nobody calls the API directly.
6. **Keys and budget:** organizer keys only ($100 OpenRouter + $100 Anthropic for the whole team). Keys live in `.env` (gitignored), never in code, logs, commits or chat. Estimate the call count before any batch run and post it to the live log.
7. **Branches:** `<area>/<topic>` from `main`. Small PRs; merge your own once it runs. `main` always runs end to end.
8. **Status:** each PR adds one file `status/<HHMM>-<who>-<slug>.md` with one line: done / next / blocked.
9. **Decisions:** one line in `docs/DECISIONS.md`. Once written, agents stop proposing alternatives.
10. **Numbers:** every number in the README or slides comes from a file in `results/`, produced by our code. Never round, never retype by hand.
11. **Insights, limitations, weird model behavior** go in `NOTES.md` as you hit them. Slide 5 and the README come from there.
12. **Disclose** reused components and any manual step (the README has a section for both). All code is written today.

## Live log
Post after every meaningful step (started, decided, finished, stuck, learned):
`LOG_WHO="Alex's agent" scripts/log "validate: pixel check passing on calendar tasks (#7)"`.
Read everything with `scripts/catchup`. Too much sharing is fine; silence is not.

## How agents help
Build to the contracts and the owner's design. Small pieces the owner can read; explain what you wrote and why.
Don't scaffold something the team hasn't decided yet (check `docs/DECISIONS.md`); ask instead.
