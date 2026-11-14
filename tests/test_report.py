"""Tests for report/: build the page from a tiny fixture. No network, no model calls.

    uv run python -m unittest tests.test_report
"""
import contextlib
import csv
import io
import json
import re
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from report import build

COLUMNS = ["model", "task_id", "status", "parsed", "question_type", "response", "ref_answer", "correct",
           "finish_reason", "error"]
HAIKU, LUNA = "anthropic/claude-haiku-5.5", "openai/gpt-6-luna"

SUNSET_STEPS = {"flat_walk_min": 14, "uphill_contour_crossings": 11, "downhill_contour_crossings": 0,
                "minutes_for_ascent": 44, "walking_minutes": 58, "daylight_minutes": 76, "arrival": "15:08",
                "wrong_if_every_crossing_counted": 10, "wrong_if_climb_ignored": 62}


def make_tasks(d: Path, with_reports=True):
    (d / "images").mkdir(parents=True)
    tasks = [
        {"task_id": "toy-sunset-000001", "image": "images/toy-sunset-000001.png", "question":
         "A lost hiker must reach the hut. Each contour line crossed going uphill adds 4 minutes. How many minutes "
         "before sunset does the hiker arrive? Answer with a whole number.", "answer": 18, "answer_type": "integer",
         "seed": 1, "generator_version": "toy-1.0.0", "question_type": "toy.sunset", "family": "toy",
         "difficulty": 3, "steps": SUNSET_STEPS, "checks": {"schema": True, "two_solvers": True}},
        {"task_id": "toy-flood-000002", "image": "images/toy-flood-000002.png", "question":
         "Which campsite does the water reach? Answer with the campsite name.", "answer": "C2",
         "answer_type": "label", "seed": 2, "generator_version": "toy-1.0.0", "question_type": "toy.flood",
         "family": "toy", "difficulty": 3, "checks": {"schema": True, "two_solvers": True},
         "steps": {"dam_elev_m": 326.2, "nearest_campsite_to_dam": "C3",
                   "camps": [{"camp": "C2", "elev_m": 48.5, "flooded": True},
                             {"camp": "C3", "elev_m": 47.3, "flooded": False}]}},
    ]
    for i, t in enumerate(tasks):
        Image.new("RGB", (320, 240), (240 - 40 * i, 230, 210)).save(d / t["image"])
    (d / "tasks.jsonl").write_text("".join(json.dumps(t) + "\n" for t in tasks), encoding="utf-8")
    if with_reports:
        (d / "generation_log.json").write_text(json.dumps(
            {"attempted": 3, "kept": 2, "rejected": [{"seed": 0, "reason": "near tie"}], "errors": []}))
        (d / "validation_report.json").write_text(json.dumps(
            {"checked": 2, "all_passed": 2, "cumulative_funnel": {"schema": 2, "two_solvers": 2}, "failures": {}}))
    return tasks


def make_results(d: Path, rows, with_extras=True):
    d.mkdir(parents=True)
    with open(d / "responses.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({"status": "ok", "finish_reason": "stop", "error": "", **r})
    if with_extras:
        (d / "run_config.json").write_text(json.dumps(
            {"models": [HAIKU, LUNA], "temperature": 0, "reasoning": {"effort": "high"}, "max_tokens": 64000,
             "prompt_template": "{question}\n\nFINAL ANSWER: <your answer>", "image_sent": True, "mock": False,
             "timestamp": "2026-11-14T18:00:00+00:00", "git_commit": "abcdef1234"}))
        (d / "summary.json").write_text(json.dumps({"totals": {"cost_usd_all_calls": 0.0125}}))
        (d / "raw").mkdir()
        rec = {"response": {"choices": [{"message": {"content": rows[0]["response"],
                                                     "reasoning": "I count the contours along the trail."}}],
                            "usage": {"cost": 0.0125}}}
        name = f"{rows[0]['task_id']}__{re.sub(r'[^A-Za-z0-9.-]+', '_', rows[0]['model'])}.json"
        (d / "raw" / name).write_text(json.dumps(rec))


ROWS = [
    {"model": HAIKU, "task_id": "toy-sunset-000001", "parsed": "14", "question_type": "toy.sunset",
     "ref_answer": "18", "correct": "0", "response":
     "Counting uphill crossings along the trail.\n\nThat gives about 12 uphill crossings. Climb: 12 x 4 = 48 min.\n"
     "Total 62 min.\n\nFINAL ANSWER: 14"},
    {"model": LUNA, "task_id": "toy-sunset-000001", "parsed": "10", "question_type": "toy.sunset",
     "ref_answer": "18", "correct": "0", "response": "Every crossing adds time.\n\nFINAL ANSWER: 10"},
    {"model": HAIKU, "task_id": "toy-flood-000002", "parsed": "C2", "question_type": "toy.flood",
     "ref_answer": "C2", "correct": "1", "response": "The water runs to C2.\n\nFINAL ANSWER: C2"},
    {"model": LUNA, "task_id": "toy-flood-000002", "parsed": "C3", "question_type": "toy.flood",
     "ref_answer": "C2", "correct": "0", "response": "C3 is closest.\n\nFINAL ANSWER: C3"},
]


class ReportTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def has(self, needle: str, page: str):
        self.assertTrue(needle in page, f"{needle!r} not in the page")

    def run_report(self, *argv) -> int:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return build.main(list(argv))

    def test_full_fixture(self):
        make_tasks(self.tmp / "tasks")
        make_results(self.tmp / "results", ROWS)
        out = self.tmp / "site" / "index.html"
        self.assertEqual(self.run_report("--tasks", str(self.tmp / "tasks"), "--results", str(self.tmp / "results"),
                                         "--pilot", f"{self.tmp / 'tasks'}:{self.tmp / 'results'}",
                                         "--out", str(out)), 0)
        page = out.read_text(encoding="utf-8")
        self.assertFalse("<script" in page)                             # no scripts at all
        self.has("data:image/jpeg;base64,", page)                  # images embedded
        self.has("data:image/png;base64,", page)                   # matplotlib charts embedded
        for s in ("Headline numbers", "The hardest task", "Failure gallery", "Accuracy by question type",
                  "Validity funnel", "Method and reproducibility"):
            self.has(s, page)
        self.has(">1/2<", page)                                     # Haiku 1/2
        self.has(">0/2<", page)                                     # Luna 0/2
        self.has("$0.0125", page)
        self.has("toy-sunset-000001", page)                         # the exemplar: both models wrong
        self.has("uphill contour crossings: said 12, truth 11", page)   # broken step from the reply text
        self.has("wrong method: every crossing counted", page)          # planted trap
        self.has("picked the nearest campsite to dam", page)           # named decoy

        ev = (self.tmp / "site" / "evidence.md").read_text(encoding="utf-8").splitlines()
        lines = [x[2:] for x in ev if x.startswith("- ")]
        self.assertTrue(lines)
        for line in lines:
            self.assertEqual(len(line.split(" · ")), 4, line)
        self.assertTrue(any(x.startswith("1/2 · anthropic/claude-haiku-5.5 accuracy") for x in lines))
        self.assertTrue(any(x.startswith("2/3 · tasks that passed every check") for x in lines))
        self.assertTrue(any(x.startswith("yes (4/4)") for x in lines))

    def test_missing_optional_files(self):
        make_tasks(self.tmp / "tasks", with_reports=False)
        make_results(self.tmp / "results", ROWS, with_extras=False)
        out = self.tmp / "index.html"
        self.assertEqual(self.run_report("--tasks", str(self.tmp / "tasks"), "--results", str(self.tmp / "results"),
                                         "--out", str(out)), 0)
        page = out.read_text(encoding="utf-8")
        self.has("No run_config.json", page)
        self.has("passes two_solvers", page)                        # funnel recomputed from task checks

    def test_regenerated_tasks_are_flagged(self):
        make_tasks(self.tmp / "tasks")
        stale = [dict(r, ref_answer="99") if r["task_id"] == "toy-sunset-000001" else r for r in ROWS]
        make_results(self.tmp / "results", stale)
        out = self.tmp / "index.html"
        self.assertEqual(self.run_report("--tasks", str(self.tmp / "tasks"), "--results", str(self.tmp / "results"),
                                         "--out", str(out)), 0)
        self.has("regenerated after they were scored", out.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
