# The organizers' requirements, short version (Track 2, Visual)

Full brief: the `Visual_Task_Factory_Assignment.docx` in the organizers' email. This is our summary; if they differ,
the brief wins.

## Timeline
Build window opened 9:20. **Upload ZIP by 3:30 PM ET** (`TeamName_Track2.zip`, Box link in the brief). Presentations
start 3:30, 5 minutes per team. Judging 4 to 5.

## Prizes
$5,000 / $2,500 / $1,250 to the top 3 teams **overall**. Each track's rubric score is converted to a percentage.

## Rubric (7 criteria, 0 to 5 each; weights from the kickoff slide)
| Criterion | Weight | Means |
|---|---|---|
| Realistic, useful visuals | 20% | Looks like real material of its kind, real names/units, real-world value |
| Reliable generation pipeline | 20% | Generates fresh, valid tasks from structured data |
| Fair, verifiable tasks | 15% | Needs the image, unique answer, computed from data, visible in the image |
| Task difficulty | 15% | Genuinely hard for strong models, shown by the evaluation |
| Meaningful variation | 10% | Different reasoning across tasks, not rewording or recoloring |
| Model evaluation | 10% | Real runs, consistent scoring, findings backed by results |
| Runnable submission | 10% | Judges build Docker, rebuild the 10 tasks, score them, following the README |

Tie-break: task validity and reference-answer verification, then generating fresh valid tasks.
**Invalid tasks are excluded, never counted as model failures.**

## Hard requirements
- **Ground truth:** data JSON first, image is a pure function of it, answer computed from it by code. Store data,
  seed and generator version with every task. No AI images, screenshots or freehand drawings.
- **Render check:** confirm what's visible matches the data (OCR of labels, pixel measurement, re-parsing). A mismatch invalidates the task.
- **Requires the image:** the question can't be answered without it.
- **Tolerance:** for continuous readings, state it in the prompt; tight enough to reject common wrong methods, loose
  enough for a careful human.
- **Realism:** copy the look of real software or publications; plausible titles, labels, units, names; realistic
  clutter but never unreadable; a few distinct styles; **cite 1 or 2 real references per image.**
- **Difficulty:** from the reasoning, not from illegibility or ambiguity. Domain knowledge must be textbook-level;
  state any constants.
- **Eval settings:** temperature 0, reasoning effort high, fixed max_tokens large enough. Every reported reply
  complete (`finish_reason = stop`). Retry 429/5xx/timeouts with backoff. If you change a setting, rerun every task.
  Log every raw response; report all results; never pick the best of several attempts.
- **Models:** `anthropic/claude-haiku-5.5` and `openai/gpt-6-luna` via OpenRouter (confirm the IDs).

## Deliverables
- Pipeline (`gen/`, `validate/`, `eval/`), Dockerfile at the root, dependency file, no secrets.
- 10 tasks, each with image, question, data JSON and check results, **each hand-checked** (notes in the README).
- Both models' responses on every task in `responses.csv`, plus `run_config.json` and raw replies.
- Pilot results and the generator changes they caused.

## README (at the root) must have these headings
- **Reported folders:** exactly one task folder and one results folder
- **Pilot results:** scores (numbers) and the generator changes because of them
- **Run in Docker:** `docker build`, then two `docker run` commands passing `-e OPENROUTER_API_KEY` with a volume
  mount: (1) rebuild the 10 reported tasks from their seeds (identical images, questions, answers), evaluate both
  models and score; (2) build one fresh task. Say how to choose the seed and the model.
- **Hand check** notes mentioning every reported task
- Also: problem statement, how the pipeline works, what makes tasks hard and why models failed, key findings,
  reused components, manual interventions, limitations, each member's contribution

## Format checker
`track2-format-check.zip` → `python3 check_submission.py TeamName_Track2.zip` (standard library only). **0 FAIL
before upload.** Read every WARN.

## Presentation (5 min, max 5 slides, template in the email)
1 (30s) project, team, capability, where it matters · 2 (30s) how a task is generated, what changes between tasks ·
3 (2.5 min) live demo · 4 (1 min) results: valid/generated, each model's score, one pilot change · 5 (30s) finding,
limitation, next test. Show one exemplar task that stumped the models: image, question, reference, each model's answer.
