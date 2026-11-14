# How we ran HackPrinceton, and how to run Innodata the same way

Written by Alex's HackPrinceton director session for his Innodata session. Part A describes the full
Princeton system, with exact files, so you can copy the **process**. Part B maps it onto `innodata-hack`:
what is already there, what to add, and what to cut for a 6-hour day with teammates Alex just met.
Process scripts and docs are fine to reuse. Product code is not (write it at the event).

---

## Part A: the HackPrinceton system

### A1. The core idea
Four people and about a dozen Claude/Codex/Cursor sessions on different laptops can't read each other's
memory. **The repo is the only shared brain.** Everything that matters is written into it, and every agent
reads it at the start of every session and before every task. One person (Alex) is the **director**: his
word lands in the repo as `directive` issues that every agent sees automatically.

### A2. Repo layout (process files only)
```
AGENTS.md                      canonical rules for every AI tool (what, golden path, owners, rules)
CLAUDE.md                      one line: @AGENTS.md
GEMINI.md, .cursor/rules/team.mdc, .github/copilot-instructions.md   pointers to AGENTS.md
.claude/settings.json          hooks: SessionStart → scripts/catchup; UserPromptSubmit → scripts/directives-check
.github/CODEOWNERS             Alex reviews AGENTS.md, DECISIONS.md, contracts/, DIRECTOR.md
.github/pull_request_template.md
.github/ISSUE_TEMPLATE/task.md
.env.example                   every key name, empty values
contracts/                     shared types (Python + TS) + fixtures/ (fake data everyone builds against)
docs/BRIEFING.md               "## Now" section: the latest shared context, kept current by the director's session
docs/DECISIONS.md              one line per decision; once written, nobody re-argues it
docs/SPEC.md                   locked spec: golden path, modules with core/bold/stretch layers, API table, owners
docs/DEMO.md                   the demo, second by second, written BEFORE building
docs/EVIDENCE.md               every number in the pitch, with how it was measured
docs/DIRECTOR.md               how directives and the director agent work (+ the agent's prompt)
docs/TEAM.md                   where each kind of information lives + the agent protocol
docs/HANDOFF.md                when people leave: what works, how to run it, priorities by owner
docs/EVENT.md, TOOLS.md, SETUP.md, WINNERS.md, STRATEGY.md   event facts, APIs, onboarding, research
scripts/log | catchup | directive | directives-check | dev
status/<YYYY-MM-DDTHHMM>-<who>-<slug>.md   one line per PR: done / next / blocked
```

### A3. AGENTS.md (the one file every tool reads)
Sections, in order:
1. **What it is**, in two sentences, plus links to SPEC and DEMO.
2. **Golden path**: the demo flow that must always work on `main`, also in mock mode.
3. **Team and ownership table**: person → paths only their agents edit. The director owns the rules files.
4. **How agents help**: the team designs, agents build what's designed in small readable pieces. No scaffolding whole apps unasked.
5. **Money rule (hard)**: no paid APIs, free tiers or sponsor credits only, stop and ask if billing appears.
6. **Director**: directives are binding; ack, do first, log, close. Only Alex and the director agent issue them; teammates use `request` issues.
7. **Live log**: everyone posts after every meaningful step.
8. **Read next**: pointers to the docs.
9. **Numbered rules**: start routine, stay in your path, contracts first, mock mode, branches `<area>/<topic>`, merge small, status file per PR, decisions are final, numbers from EVIDENCE, secrets never committed, golden-path check before merge.
10. **Event rules that bite**: deadline, demo length, code-written-at-event.

### A4. Communication channels (and what goes where)
| Information | Where | Who |
|---|---|---|
| Rules, owners, golden path | `AGENTS.md` | director |
| Latest shared context | `docs/BRIEFING.md` "## Now" | director's session, after every substantive answer |
| Decisions | `docs/DECISIONS.md` | whoever decided, right away |
| Shared data shapes | `contracts/` + fixtures | by PR, with a DECISIONS line |
| Tasks | GitHub issues, one per Claude session | anyone |
| Asking another area | issue labeled `request` or the area label, mention the owner | anyone (never a DM: agents can't read DMs) |
| Orders | issue labeled `directive` | Alex / director agent only |
| Everything as it happens | **live log = issue #1**, via `scripts/log` | every person and agent |
| Progress | one new `status/` file per PR | every PR |
| Numbers | `docs/EVIDENCE.md` | whoever measured |
| Keys | team DM only, then `.env` | never the repo |
| Human chatter | team chat; anything that matters gets copied into the repo | everyone |

### A5. The scripts (exact behavior)
- **`scripts/log "msg"`**: comments `**<LOG_WHO or git name>** · HH:MM · msg` on issue #1.
  Agents set `LOG_WHO="Julian's agent"` so it's clear who wrote it.
- **`scripts/catchup`** prints, in order:
  1. the BRIEFING "Now" section
  2. the latest director-agent update (from branch `claude/director-log`)
  3. open directives
  4. the last 25 live-log entries
  5. the last 15 commits on `origin/main`
  6. open issues
  7. the 10 newest status lines
- **`scripts/directive "<who>: <what>"`**: creates an issue `DIRECTIVE: …` labeled `directive`, with the body
  "Agents: comment ack/done, do this before other work, log it, close when done". It also logs
  "📌 New directive: … (url)".
- **`scripts/directives-check`**: prints open directives, and nothing when there are none.
- **`.claude/settings.json` hooks**:
  - `SessionStart` runs `catchup`, so every Claude session starts with full context.
  - `UserPromptSubmit` runs `directives-check`, so open directives show up on **every message**.
  - Other tools (Codex, Cursor, Copilot, Gemini) are told in AGENTS.md to run both by hand before each task.

(Copy them from `~/Desktop/hackprinceton-f26/scripts/` and change the `REPO=` / `--repo` value.)

### A6. GitHub setup
- **Labels:**
  - areas: `area:web`, `area:agent`, `area:core`, `area:integrations`
  - process: `contracts`, `blocked`, `demo-critical`, `question`, `request`
  - **`directive`** (black, "Instruction from the director; do first")
- **Issue #1 = live log** (pinned). Issues are numbered by module (#23 keys, #24 mock API, #26 agents, #32 web shell…), one per Claude session.
- **CODEOWNERS** on the rules files. Branch protection: PR required, code-owner review, 0 approvals, `enforce_admins` off so Alex can push docs directly.
  (Branch protection needs the repo to be public or GitHub Pro.)
- **PR template**:
  - what changed / how I tested it (mock mode? golden path?) / what other areas need to know
  - checkboxes: stayed in my area, added a status line, env vars in `.env.example`, DECISIONS line for contract changes
- **Merging:** authors squash-merge their own PR once it works. No single-merger bottleneck (the lesson from Cal Hacks).
- **Collaborators** added by GitHub username in the first 10 minutes. GitHub apps: Claude (for cloud agents) and Cursor, if teammates use them.

### A7. Specs and contracts first
- Hour 1: `docs/SPEC.md` (v1 locked) with the golden path, modules M1 to M7, each split into **core / bold / stretch** layers, an API table, and owners.
- `contracts/models.py` + `contracts/types.ts` + `contracts/fixtures/*.json`, validated with pydantic.
  Every module built against fixtures in parallel, so nobody waited on anybody.
- **Mock mode** (`MOCK=true`) for every external API. Real adapters fall back to mock on error, so the demo never dies on venue Wi-Fi.

### A8. The director system
- **Alex's main Claude session acts as director's staff**:
  - keeps BRIEFING "Now" current
  - sends directives itself with `scripts/directive` (Alex doesn't run it)
  - logs every step
  - gives Alex **only paste-ready text** for humans
- **Directives** are short and assignable: "Farhan: read docs/HANDOFF.md. Your Saturday order: (1)…, (2)…".
  Agents comment "ack", do it first, then close it.
- **Director agent**: a scheduled cloud routine (hourly) that reads all the state and writes a "📍 Director update HH:MM", at most 12 lines:
  - on track / at risk
  - each person: now → next
  - blockers
  - the top 3 priorities

  It may only issue *process* directives, never product ones. The prompt is in `docs/DIRECTOR.md`.
  It needed the Claude GitHub App installed on the repo to post.
- **Decisions are final once written.** Arguments end in DECISIONS.md.

### A9. Daily rhythm that worked
1. Idea picked, then spec locked, then contracts and fixtures, then **everyone builds in their own folder at once**.
2. Each module merged as a small PR as soon as it ran.
3. The director's session built the glue (web shell, server pipeline) overnight, then **clicked through the real
   demo in a browser** and fixed what broke. Testing with curl alone missed a page crash, so always click through.
4. `docs/HANDOFF.md` plus one directive per person when people left, so work continued without Alex.

### A10. What we'd keep / change
- Keep: repo-as-brain, hooks, directives, live log, contracts and fixtures, folder ownership, mock mode, EVIDENCE file.
- Painful:
  - Too many docs (19 files). Agents read them, but humans didn't.
  - The cloud director agent was blocked on GitHub permissions for hours.
  - Teammates went quiet in the morning with no check-in.

---

## Part B: running Innodata the same way (6 hours, strangers, 3:30 PM ZIP)

### B1. Already in `innodata-hack` (good)
AGENTS.md with a golden path, ownership table, 11 rules, money/key rules, `contracts/SCHEMA.md`,
`docs/DECISIONS.md`, `docs/BRIEF.md`, `docs/ARCHITECTURE.md`, `docs/IDEATION.md`, `NOTES.md`,
`status/`, `scripts/log`, `scripts/catchup`, `.claude/settings.json`, folders `gen/ validate/ eval/ results/ tasks/`.

### B2. Add in the next 15 minutes (Alex's session does all of it)
1. **Issue #1 "Live log"**, pinned, if it isn't already. Check that `scripts/log` points at it.
2. **Directive system**: copy `scripts/directive` and `scripts/directives-check`, add the `UserPromptSubmit` hook,
   create the `directive` and `request` labels, and add the "Director" paragraph to AGENTS.md (A3 item 6).
   With strangers, word it as a **team lead role the team agrees to**, not orders. Something like "Alex
   coordinates; `directive` issues are agreed team tasks; ack, do first, close".
3. **Labels** matching the folders: `area:gen`, `area:validate`, `area:eval`, `area:report`, plus `blocked`, `demo-critical`.
4. **Issues**, one per Claude session, each with owner, acceptance test and folder. Example: "#3 gen/charts: 50 items
   pass `validate` with seed 0..49".
5. **PR template** (A6) and **CODEOWNERS** on `AGENTS.md`, `contracts/`, `docs/DECISIONS.md`.
6. **Pointer files** for teammates' tools: `GEMINI.md`, `.cursor/rules/team.mdc`, `.github/copilot-instructions.md`,
   each saying "read AGENTS.md; run scripts/catchup before each task".
7. **`docs/EVIDENCE.md`** (or `results/SUMMARY.md` generated by code): the only source of numbers for the slides and README.
8. **`scripts/check`**: one command that runs the golden path (generate seed 0 → validate → eval with the mock
   model → results row). Run it before every merge. It doubles as the organizers' reproducibility proof.
9. Add teammates as collaborators the moment you have their usernames (`tech-cosmos`, `dl3832`, `WindHurtLZ`).
   Send them the paste message in B6.

### B3. Cut for today
- No cloud director agent: too slow to set up. Alex's session does a director update by hand every 45 minutes (B4).
- No SPEC with 7 modules: `docs/SPEC.md` is one page. Item format, the 2 or 3 capabilities, checks, metrics, owner per folder.
- No HANDOFF doc: everyone is in the room.
- Fewer docs: AGENTS, DECISIONS, SPEC, BRIEF, NOTES, EVIDENCE. That's it.

### B4. Director loop (every ~45 min, Alex's session)
1. Run `scripts/catchup`, `gh pr list`, `git log origin/main`.
2. Post a "📍 Director update HH:MM" to the live log:
   - on track / at risk against the clock in B5
   - each person: now → next
   - blockers
   - the top 3 for the next hour
3. Send directives for anything stuck: "dl3832: merge gen/tables PR, then run 100 items through validate".
4. Update BRIEFING/NOTES with anything the whole team should know (API quirks, model weirdness, decisions).
5. Give Alex one paste-ready message if the humans need to hear it.

### B5. Gated clock (3:30 PM ZIP, aim 3:10)
| By | Gate (if missed: cut scope, don't slip) |
|---|---|
| +0:30 | Track and idea in DECISIONS, roles in AGENTS.md, issues filed, everyone's agent ran catchup |
| +1:00 | `contracts/SCHEMA.md` frozen + 5 fixture items; each folder builds against fixtures |
| +1:45 | **One capability end to end** on `main`: generate → validate → eval (mock) → results row |
| +2:30 | Real model numbers on ~50 items, cached; budget check posted to the log |
| +3:30 | All capabilities + difficulty knobs; a few hundred items; validator rejection stats |
| 2:15 PM | Charts with error bars, failure gallery, NOTES → insights. **Feature freeze** |
| 2:45 PM | README, Dockerfile runs clean from a fresh clone, ZIP built by script, slides |
| 3:10 PM | ZIP uploaded. Rehearse the 5-minute talk twice |

### B6. Paste message for the team (once the repo is ready)
```
Repo: github.com/Alex-Epstein/innodata-hack (I'm adding you now). Tell your AI tool to read AGENTS.md first, it has everything: what we're building, who owns which folder, the rules.
How we stay in sync: every agent runs scripts/catchup before each task and posts one line to the live log (issue #1) with scripts/log after each step. Tasks are GitHub issues, one per person/session. Shared format is contracts/SCHEMA.md, don't change it without a line in docs/DECISIONS.md.
Stay in your folder, small PRs, merge your own once scripts/check passes. Model calls only through eval/'s client (cached, so we don't burn the $200). Keys only in .env.
Gates: one item end to end in ~1h45, real numbers by +2:30, freeze 2:15, ZIP up by 3:10.
```

### B7. Rules that carry over word for word
- Ground truth from code, never from a model or a person reading the image.
- One cached model client; estimate call count before any batch; never a personal paid key.
- Every number from `results/` or EVIDENCE; never round, never retype.
- Click through / run the full golden path from a fresh clone before calling anything done.
- Paste-only messages for humans; directives for agents.
- No ChatOverflow notes about Innodata work.
