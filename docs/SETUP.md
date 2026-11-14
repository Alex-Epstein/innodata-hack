# Setup

**Humans:** paste this into your AI agent (Claude Code, Codex, Cursor, anything with a terminal) and approve what it asks:

> Set me up for our hackathon repo by following https://github.com/Alex-Epstein/innodata-hack/blob/main/docs/SETUP.md (the "Agent steps" section). My GitHub username is ___.

---

## Agent steps
Do these in order, yourself. Only stop to ask your user where a step says so. Never print a key.

1. **GitHub CLI.** Run `gh auth status`. If it isn't signed in, ask your user to run `gh auth login` (browser
   login), then continue. Check that `gh api user --jq .login` matches the username your user gave you.
2. **Accept the repo invite** (skip if already a collaborator):
   ```bash
   id=$(gh api user/repository_invitations --jq '.[] | select(.repository.full_name=="Alex-Epstein/innodata-hack") | .id')
   [ -n "$id" ] && gh api -X PATCH "user/repository_invitations/$id"
   ```
   If there's no invite and `gh api repos/Alex-Epstein/innodata-hack/collaborators/$(gh api user --jq .login)` fails,
   tell your user to ask Alex to add them, and stop.
3. **Clone or update.** If the repo isn't on disk: `git clone https://github.com/Alex-Epstein/innodata-hack ~/innodata-hack`.
   Then `cd` into it and `git pull`. Work from this folder from now on, and tell your user to reopen their agent here
   next time.
4. **Tools.** Check `uv --version` (if missing: `curl -LsSf https://astral.sh/uv/install.sh | sh`) and `docker info`
   (if it fails, tell your user to start Docker Desktop; continue anyway). Python comes through uv.
5. **Keys.** If `.env` doesn't exist, `cp .env.example .env`. Then check without printing values:
   `grep -cE '^OPENROUTER_API_KEY=.+' .env`. If that prints 0, ask your user to open `.env` in their editor and paste
   the team keys Alex posted in the team chat after `OPENROUTER_API_KEY=` and `ANTHROPIC_API_KEY=`, save, and tell
   you. Re-check. Never ask for the key in chat, and never echo or cat `.env`.
6. **Read and get your ticket.**
   - Read `AGENTS.md` fully, then run `scripts/catchup` and read `docs/BRIEFING.md`.
   - If an open `directive` names your user or "everyone", that's the task.
   - Otherwise, if an issue is already assigned to your user, that's the task.
   - Otherwise take the **first issue in BRIEFING's "Claim order" with no assignee**:
     `gh issue edit <N> --repo Alex-Epstein/innodata-hack --add-assignee @me`. Then re-check
     `gh issue view <N> --repo Alex-Epstein/innodata-hack --json assignees`. If someone else also got assigned in
     the meantime, remove yourself (`--remove-assignee @me`) and take the next one.
   - Tell your user which issue they now own, in one sentence.
7. **Announce.** `LOG_WHO="<username>'s agent" scripts/log "joined; took #<N>: <title>"`.
8. **Start the issue.** Read it, branch `<area>/<topic>`, and follow "How we work" in `AGENTS.md` until its
   "Done when" is met. Then close it, log it, and go back to step 6 for the next one.
