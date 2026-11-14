"""validate/: every automatic check on a task (organizers' required folder name).

    uv run python -m factory validate --tasks tasks/<set> [--drop-invalid] [--blind-results results/extra/blind]
    uv run python -m validate --tasks tasks/<set>          (same thing)

From code: `iter_checks(tasks_dir, rec)` yields (name, passed, detail) one check at a time;
`validate_set(tasks_dir, ...)` runs everything, writes `checks` into tasks.jsonl and validation_report.json.
"""
from validate.checks import CHECKS, NAMES, Ctx  # noqa: F401
from validate.run import iter_checks, needs_image_from_blind, validate_set, validate_task  # noqa: F401
