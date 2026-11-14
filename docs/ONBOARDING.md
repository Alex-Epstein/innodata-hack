# Onboarding: paste this to your AI agent

**Humans, do this first (2 min):**
1. Accept the GitHub invite (email, or github.com/Alex-Epstein/innodata-hack/invitations).
2. `git clone https://github.com/Alex-Epstein/innodata-hack && cd innodata-hack`
3. `gh auth login` (if you haven't), and install `uv` if missing (`curl -LsSf https://astral.sh/uv/install.sh | sh`).
4. Create `.env` in the repo root with the two keys Alex posts in the team chat:
   `OPENROUTER_API_KEY=...` and `ANTHROPIC_API_KEY=...`
5. Open your AI tool **in the repo folder** and paste the prompt below (fill in your GitHub name).

---

## The prompt (paste to Claude Code / Cursor / Codex / Copilot / Gemini)

```
I'm <MY GITHUB USERNAME> on the Innodata hackathon team (Visual Task Factory track). This repo is our team's shared brain.

1. Read AGENTS.md fully, especially the Roles box and "Start here". Alex (Alex-Epstein) is the team lead; I'm a ticket-taker, so you only work on an issue I've claimed, inside its folder, and you never re-plan the project or edit lead-owned files.
2. Do the "Start here" setup check and fix what's missing (ask me before installing anything big).
3. Run scripts/catchup and scripts/directives-check. If there's an open directive for me or "everyone", do that first.
4. Read docs/BRIEFING.md, docs/BRIEF.md and contracts/SCHEMA.md.
5. Show me the open unclaimed issues and recommend the one that fits me best. Once I say yes, comment "claim (<my name>)" on it and post to the live log with: LOG_WHO="<my name>'s agent" scripts/log "claimed #N: <title>".
6. Then work the issue: branch <area>/<topic>, small steps I can follow, explain what you write. Log each milestone with scripts/log. Finish with a PR using the template plus a status/ line, and merge once the issue's "Done when" is met.

Rules that never bend: images from code only; answers computed from data by code, never by a model; every model call goes through eval/'s cached client; keys only in .env, never printed or committed; stay in your folder; organizer keys only ($200 for the whole team).
```

---

## If Alex assigns you a specific ticket
Add one line at the end of the prompt: `Alex assigned me issue #N. Skip step 5 and start on it.`
