"""Tests for validate/review.py (advisory LLM reviewer) on the example family. No network: MOCK=1, and urlopen
is patched to fail if anything tries to call out.

    uv run python -m unittest discover -s tests -t .
"""
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from factory.__main__ import main as cli
from factory.tasks import load_tasks
from validate import review


def quiet(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return fn(*a, **kw)


def no_network(*a, **kw):
    raise AssertionError("the reviewer tried to call the network")


class ReviewTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.tasks = self.tmp / "tasks"
        self.assertEqual(quiet(cli, ["generate", "--family", "example", "--template", "tallest", "--difficulty", "3",
                                     "--seeds", "0-9", "--out", str(self.tasks)]), 0)
        self.env = mock.patch.dict(os.environ, {"REVIEW_CACHE_DIR": str(self.tmp / "cache")})
        self.env.start()
        os.environ.pop("MOCK", None)            # scripts/check exports MOCK=1; tests set it where they need it
        self.net = mock.patch("urllib.request.urlopen", no_network)
        self.net.start()

    def tearDown(self):
        self.net.stop()
        self.env.stop()
        self._tmp.cleanup()

    def test_mock_run_writes_report_and_leaves_tasks_alone(self):
        before = (self.tasks / "tasks.jsonl").read_bytes()
        n = len(load_tasks(self.tasks))
        with mock.patch.dict(os.environ, {"MOCK": "1"}):
            self.assertEqual(quiet(review.main, ["--tasks", str(self.tasks)]), 0)
        self.assertEqual((self.tasks / "tasks.jsonl").read_bytes(), before)       # advisory: nothing changes
        rep = json.loads((self.tasks / "review_report.json").read_text())
        self.assertEqual(rep["reviewed"], n)
        self.assertEqual(rep["model"], "claude-sonnet-5-5")
        self.assertEqual({r["task_id"] for r in rep["reviews"]}, {r["task_id"] for r in load_tasks(self.tasks)})
        self.assertTrue(all(r["verdict"] == "ok" and r["mock"] and not r["cached"] for r in rep["reviews"]))
        self.assertFalse((self.tmp / "cache").exists())                            # mock replies are never cached

    def test_limit_and_dry_run(self):
        with mock.patch.dict(os.environ, {"MOCK": "1"}):
            rep = quiet(review.review_set, self.tasks, 3)
            plan = quiet(review.review_set, self.tasks, 2, dry_run=True)
        self.assertEqual(rep["reviewed"], 3)
        self.assertEqual(plan["planned_new_calls"], 2)
        self.assertGreater(plan["estimated_max_usd"], 0)

    def test_prompt_has_question_answer_and_steps(self):
        rec = load_tasks(self.tasks)[0]
        text = review.task_text(rec)
        self.assertIn(rec["question"], text)
        self.assertIn(f"REFERENCE ANSWER (computed by code, answer_type {rec['answer_type']}): {rec['answer']}", text)
        for s in rec["steps"]:
            self.assertIn(s, text)

    def test_cached_review_is_read_without_network(self):
        rec = load_tasks(self.tasks)[0]
        key = review._key_for(rec, self.tasks)[0]
        reply = {"issues": [{"kind": "ambiguity", "detail": "bars B and C look the same height"}],
                 "realism_notes": "clean chart", "verdict": "ok"}
        cached = {"key": key, "task_id": rec["task_id"], "model": review.MODEL, "error": "", "mock": False,
                  "response": {"stop_reason": "end_turn", "content": [{"type": "text", "text": json.dumps(reply)}],
                               "usage": {"input_tokens": 1500, "output_tokens": 120}}}
        (self.tmp / "cache").mkdir()
        (self.tmp / "cache" / f"{key}.json").write_text(json.dumps(cached))
        out = review.review_task(rec, self.tasks)
        self.assertTrue(out["cached"])
        r = review.parse_review(out)
        self.assertEqual(r["verdict"], "flag")                    # verdict follows the issues
        self.assertEqual(r["issues"][0]["kind"], "ambiguity")

    def test_bad_replies_are_errors(self):
        def rec(resp):
            return {"error": "", "response": resp}
        self.assertEqual(review.parse_review(rec({"stop_reason": "max_tokens", "content": []}))["verdict"], "error")
        self.assertEqual(review.parse_review(rec({"stop_reason": "refusal", "content": []}))["verdict"], "error")
        bad = {"stop_reason": "end_turn", "content": [{"type": "text", "text": "not json"}]}
        self.assertIn("not the review JSON", review.parse_review(rec(bad))["error"])
        self.assertEqual(review.parse_review({"error": "api_error", "response": None})["verdict"], "error")


if __name__ == "__main__":
    unittest.main()
