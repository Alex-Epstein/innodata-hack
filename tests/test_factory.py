"""Tests for factory/ and validate/ with the example family. No network: models run with MOCK=1.

    uv run python -m unittest discover -s tests -t .
"""
import contextlib
import csv
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from factory import registry
from factory.__main__ import main as cli
from factory.tasks import build_task, load_tasks, parse_seeds
from validate import checks
from validate.run import validate_set


def run_cli(*argv) -> int:
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return cli(list(argv))


class FactoryTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.tasks = self.tmp / "tasks"
        self.assertEqual(run_cli("generate", "--family", "example", "--template", "tallest", "--difficulty", "3",
                                 "--seeds", "0-9", "--out", str(self.tasks)), 0)

    def tearDown(self):
        self._tmp.cleanup()

    def test_registry_finds_example(self):
        fams = registry.discover(quiet=True)
        self.assertIn("example", fams)
        self.assertTrue(getattr(fams["example"], "TEST_ONLY", False))

    def test_generate_writes_records_and_log(self):
        recs = load_tasks(self.tasks)
        log = json.loads((self.tasks / "generation_log.json").read_text())
        self.assertEqual(log["attempted"], 10)
        self.assertEqual(log["kept"], len(recs))
        self.assertEqual(log["rejected_count"], 10 - len(recs))
        self.assertTrue(all(r["reason"] for r in log["rejected"]))
        for r in recs:
            self.assertEqual(r["question_type"], "example.tallest")
            self.assertEqual(r["generator_version"], "example-1.0.0")
            self.assertTrue((self.tasks / r["image"]).is_file())
            self.assertTrue((self.tasks / r["data"]).is_file())
            self.assertTrue((self.tasks / "layout" / f"{r['task_id']}.json").is_file())
            self.assertNotIn("layout", r)

    def test_validate_all_pass_and_report(self):
        self.assertEqual(run_cli("validate", "--tasks", str(self.tasks)), 0)
        recs = load_tasks(self.tasks)
        for r in recs:
            self.assertEqual(set(r["checks"]), set(checks.NAMES))
            self.assertTrue(all(r["checks"].values()), r["checks"])
        rep = json.loads((self.tasks / "validation_report.json").read_text())
        self.assertEqual(rep["all_passed"], len(recs))
        self.assertEqual(rep["generation"]["attempted"], 10)

    def test_rebuild_identical_then_detects_tampering(self):
        self.assertEqual(run_cli("rebuild", "--tasks", str(self.tasks)), 0)
        r = load_tasks(self.tasks)[0]
        png = self.tasks / r["image"]
        png.write_bytes(png.read_bytes() + b"\0")
        self.assertEqual(run_cli("rebuild", "--tasks", str(self.tasks)), 1)

    def test_validate_catches_broken_tasks_and_drops_them(self):
        recs = load_tasks(self.tasks)
        recs[0]["answer"] = "Z"                                    # wrong answer: two_solvers fails
        recs[1]["answer_type"] = "number"                          # schema fails
        write = "".join(json.dumps(r) + "\n" for r in recs)
        (self.tasks / "tasks.jsonl").write_text(write)
        rep = validate_set(self.tasks, drop_invalid=True, verbose=False)
        self.assertGreaterEqual(rep["per_check"]["two_solvers"]["failed"], 1)
        self.assertGreaterEqual(rep["per_check"]["schema"]["failed"], 1)
        self.assertIn(recs[0]["task_id"], rep["dropped"])
        self.assertEqual(len(load_tasks(self.tasks)), len(recs) - 2)
        self.assertFalse((self.tasks / recs[0]["image"]).exists())

    def test_needs_image_from_blind_run(self):
        recs = load_tasks(self.tasks)
        blind = self.tmp / "blind"
        blind.mkdir()
        with open(blind / "responses.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["model", "task_id", "correct"])
            w.writeheader()
            for i, r in enumerate(recs):
                for m in ("m1", "m2"):
                    w.writerow({"model": m, "task_id": r["task_id"], "correct": "1" if i == 0 else "0"})
        rep = validate_set(self.tasks, blind_results=blind, verbose=False)
        self.assertEqual(rep["per_check"]["needs_image"]["failed"], 1)
        self.assertFalse(load_tasks(self.tasks)[0]["checks"]["needs_image"])

    def test_render_check_catches_wrong_pixels(self):
        from PIL import Image
        r = load_tasks(self.tasks)[0]
        png = self.tasks / r["image"]
        with Image.open(png) as im:
            size = im.size
        Image.new("RGB", size, "white").save(png)
        rep = validate_set(self.tasks, verbose=False)
        self.assertTrue(rep["failures"][r["task_id"]].keys() >= {"render_matches_data", "reproducible"})

    def test_eval_mock(self):
        with mock.patch.dict(os.environ, {"MOCK": "1", "EVAL_CACHE_DIR": str(self.tmp / "cache")}):
            self.assertEqual(run_cli("eval", "--tasks", str(self.tasks), "--out", str(self.tmp / "res")), 0)
        with open(self.tmp / "res" / "responses.csv", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 2 * len(load_tasks(self.tasks)))
        self.assertTrue(all(r["finish_reason"] == "stop" and r["question_type"] == "example.tallest" for r in rows))

    def test_fresh_mock(self):
        out = self.tmp / "fresh"
        with mock.patch.dict(os.environ, {"MOCK": "1", "EVAL_CACHE_DIR": str(self.tmp / "cache")}):
            self.assertEqual(run_cli("fresh", "--seed", "3", "--family", "example", "--out", str(out)), 0)
        rec = load_tasks(out)[0]
        self.assertTrue(all(rec["checks"].values()))
        self.assertTrue((out / "results" / "responses.csv").is_file())


class UnitTest(unittest.TestCase):
    def test_parse_seeds(self):
        self.assertEqual(parse_seeds("0-3"), [0, 1, 2, 3])
        self.assertEqual(parse_seeds("1000-1002,7"), [1000, 1001, 1002, 7])

    def test_answer_leak(self):
        q = "Which feeder trips first? Answer with its name."
        self.assertTrue(checks._leaks("F-12", "Feeder F-12 trips first. Which feeder trips first?")[0])
        self.assertFalse(checks._leaks("F-12", "Of F-11, F-12 and F-13, which trips first?")[0])
        self.assertFalse(checks._leaks("A", "Is it a bar? " + q)[0])           # 'a' is not 'A'
        self.assertFalse(checks._leaks("Pump House 2", q)[0])

    def test_schema_tolerance(self):
        base = {"task_id": "x-t-000001", "image": "i.png", "question": "How far? Within 0.5 km.",
                "answer": 3.25, "answer_type": "number", "seed": 1, "generator_version": "x-1",
                "question_type": "x.t", "family": "x", "difficulty": 1, "data": "d.json", "references": ["r"]}
        ctx = checks.Ctx(tasks_dir=Path("/nonexistent"), rec=dict(base))
        _, ok, detail = checks.schema(ctx)
        self.assertIn("without a tolerance", detail)
        ctx.rec["tolerance_abs"] = 0.5
        self.assertNotIn("tolerance", checks.schema(ctx)[2])
        ctx.rec["tolerance_rel"] = 0.05
        self.assertIn("exactly one", checks.schema(ctx)[2])

    def test_save_png_is_deterministic(self):
        from factory.render import new_figure, save_png
        with tempfile.TemporaryDirectory() as d:
            hashes = []
            for i in range(2):
                fig = new_figure(200, 100)
                fig.add_subplot().plot([0, 1], [1, 0])
                hashes.append(save_png(fig, Path(d) / f"{i}.png"))
            self.assertEqual(hashes[0], hashes[1])

    def test_build_is_deterministic(self):
        fam = registry.get("example")
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            ra, rb = build_task(fam, 1, "tallest", 3, a), build_task(fam, 1, "tallest", 3, b)
            self.assertEqual(ra["image_sha256"], rb["image_sha256"])
            self.assertEqual(ra["data_sha256"], rb["data_sha256"])


if __name__ == "__main__":
    unittest.main()
