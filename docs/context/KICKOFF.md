# Kickoff talk (condensed from the transcript) + Alex's notes

## Alex's notes during the talk
- The pitch has to be very good, with an impressive, engaging demo.
- It's very technical, so we have to explain it well.
- The guidelines are strict: follow them first, then make it cool.
- "Restricted budget" means the API key budget.
- Go up and talk to the mentors.
- How far outside the box can we go, given the presentation template? It reads like an assignment.
- Keep thinking about limitations and insights throughout: what we didn't have time for, what we'd do differently.
- Aim to be done by 3:30.

## What the speaker said (every fact, condensed)
**Framing.** Today we're effectively building **RL environments** for training agents. The judging point: don't
create one task, **create something that creates many tasks** (a pipeline, a factory).

**Coding track.** Input: a prescribed repo at a pinned, declared commit (Python, JS or C++), so everyone is
apples to apples. Task: a **new** feature spec (not one already in the repo's history, which would be cheating).
Answer: a reference implementation. Evidence: tests. Package format is Harbor: `task.toml` (identity, base commit,
config like runtime budget), `instruction.md` (the prompt), `solution/` (the reference patch, hidden from the
model), `tests/`, and a Dockerfile (everything runs in Docker). Tests aren't sent to the model, and only results
are judged, so tests must be deterministic. Before/after: at the base repo feature tests fail and regression tests
pass; with the reference both pass. Benchmark against **Haiku 5.5** ("somewhat easier to stump", saves budget).
They decided on **3 rollouts per task** instead of 5; a task is stumped if the model fails at least 2 of 3.

**Visual track.** Input: structured data. You programmatically generate images from a known setting, so you know
the golden answer. Example: a grocery aisle where you know where every cereal box is. Example: a social network
with 100 nodes, "who are Adam's second-degree connections?". **Images come from code, never from an AI model**,
so the solution can be verified by code. Tasks must be "rooted in logic", not wild prompts. Produce **at least 10
tasks**, but build a factory that could make many more. Evaluate **Claude Haiku 5.5 and GPT-6 Luna**
("baseline-ish" models). Package: README, results folder, task folder, eval source code (model calls, responses,
scoring, reporting), validation (the computed original answer). A reference implementation and format checker are
provided. Packaging matters: "clients don't pay for something that isn't packaged well." Organizers will help with
structure if you're stuck.

**Scoring.** Coding is scored out of 100, visual out of 35, and both are **converted to percentages**, so neither
track is advantaged.

**Model evaluation means:** send the image and question to the model under test, get an answer with no API error,
and score it with a proper mechanism, including numerical tolerance. If the model isn't stumped, it's still valid:
"we love to see the process."

**Keys and budget.** One Anthropic key + one OpenRouter key, **$100 each, per team** (not per person). Use only
these; using your own AI budget would be unfair. Anthropic is for benchmarking (coding track needs it) and can
also power your coding assistant. OpenRouter gives access to any model, including Anthropic ones. You can't see
your usage; **ask Amila**, per team. "Don't burn it before the demo."

**Checkpoints.** 10 to 15 min to meet the team. First 30 min: understand the participant guide and tools, agree on
the problem. Next 90 min: make one task by hand, then shape it into a pipeline. By hour 3: something promising,
start packaging. **By 3:30: everything done.** Submission is the ZIP to Box, plus a presentation.

**Presentation.** About 5 minutes per team (maybe up to 10 with Q&A, depending on team count). Use the template
(a few required slides). Cover: the approach, a walkthrough of the problem your pipeline tackles, **one task you
created**: if it fails, why; if it doesn't, what you'd have done differently with more time.

**Teams.** Assigned by the organizers; Jason/Kolton handle team questions.
