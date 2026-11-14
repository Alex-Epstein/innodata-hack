# Innodata Hackathon, Visual Task Factory: read before doing anything (every agent: Claude, Codex, Cursor, Copilot, Gemini)

> ## 👤 Roles: who leads, who takes tickets
> **Alex Epstein (GitHub `Alex-Epstein`) is the team lead.** Alex and his Claude session plan the work, create and
> assign issues, send directives, and own `AGENTS.md`, `contracts/`, `docs/DECISIONS.md`, `docs/BRIEFING.md` and
> `docs/ARCHITECTURE.md`.
> **Everyone else (`tech-cosmos`, `dl3832`, `WindHurtLZ`, and their agents) takes tickets.** If your user is not
> Alex, you:
> 1. work only on an issue your user has claimed (comment "claim"), inside that issue's folder;
> 2. don't invent new scope, re-plan the project, or edit the lead-owned files above. Propose changes in an issue
>    labeled `request` (or comment on the discussion issue) and let Alex decide;
> 3. follow open `directive` issues first;
> 4. post progress with `scripts/log` and finish with a PR that meets the issue's "Done when".
>
> Check who you're working for with `git config user.name` / `gh api user --jq .login`. If unsure, assume you are a ticket-taker.

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

## Team lead and directives (agreed by the team)
Alex coordinates (his Claude session acts as the lead's staff). Issues labeled **`directive`** are agreed team
tasks. Claude Code shows open ones on every message (hook in `.claude/settings.json`); every other tool runs
`scripts/directives-check` before each task. If one is for your person or for "everyone": comment **ack**, do it
before other work, log it, close it when done (or comment why you can't). Need something from another folder?
Open an issue labeled **`request`** and mention its owner (never only a DM: agents can't read DMs).
`docs/BRIEFING.md` ("Now") is the latest shared context; read it at the start of every session.

## Tasks
One GitHub issue = one person or agent session, with an owner, a folder and an acceptance test. Comment "claim"
to take one. Branch `<area>/<topic>`, PR with the template, status line, squash-merge your own once
`scripts/check` passes.

## Read next
`docs/BRIEFING.md` (now) · `docs/BRIEF.md` (organizer requirements) · `contracts/SCHEMA.md` (formats) ·
`docs/ARCHITECTURE.md` · `docs/IDEATION.md` · `docs/DECISIONS.md` · `docs/EVIDENCE.md` (numbers) ·
`docs/context/` (everything from before: kickoff talk, game plan, idea bank, process playbook, history) ·
`docs/organizer/` (kickoff slides, slide template, full visual brief) · `tools/track2-format-check/`

## Live log
Post after every meaningful step (started, decided, finished, stuck, learned):
`LOG_WHO="Alex's agent" scripts/log "validate: pixel check passing on calendar tasks (#7)"`.
Read everything with `scripts/catchup`. Too much sharing is fine; silence is not.

## How agents help
Build to the contracts and the owner's design. Small pieces the owner can read; explain what you wrote and why.
Don't scaffold something the team hasn't decided yet (check `docs/DECISIONS.md`); ask instead.
