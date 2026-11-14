# Innodata Hackathon: Visual Task Factory

> **Team / agents: start at `AGENTS.md`** (new here: `docs/SETUP.md`). This README becomes the submission README;
> the headings below are the ones the organizers' format checker requires. Fill them in as results land.

## Problem statement

## How the pipeline works

## Reported folders
- Tasks: `tasks/final/`
- Results: `results/final/`

## Pilot results
Filled in from `docs/EVIDENCE.md` after the pilot runs: scores per level, and the generator changes they caused.

## What makes the tasks hard, and why the models failed

## Key findings

## Hand check

## Run in Docker
Only Docker is needed. The key is passed at run time and never stored in the image. Everything a run produces is
written to `./out` on your machine (mounted at `/out` in the container).

```bash
docker build -t visual-task-factory .
mkdir -p out
export OPENROUTER_API_KEY=<your OpenRouter key>

# 1. Rebuild the 10 reported tasks from their seeds (same images, questions and reference answers),
#    then evaluate both models on them and score the answers.
docker run --rm -e OPENROUTER_API_KEY -v "$(pwd)/out:/out" visual-task-factory rebuild

# 2. Build, check, evaluate and score one fresh task.
docker run --rm -e OPENROUTER_API_KEY -v "$(pwd)/out:/out" visual-task-factory fresh --seed 4242
```

- **Seed:** `--seed N` takes any whole number; the same seed always builds the same task.
- **Model:** both models are evaluated by default (`anthropic/claude-haiku-5.5` and `openai/gpt-6-luna`). To pick
  one, add `--model anthropic/claude-haiku-5.5` (repeatable) to either command.
- **Settings** are fixed in `eval/client.py`: temperature 0, reasoning effort high, max_tokens 32000.

## Reused components

## Manual interventions

## Limitations

## Team contributions
