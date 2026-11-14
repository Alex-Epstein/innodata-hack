"""Tests for eval/. No network: the client runs with MOCK=1 or a fake transport.

    uv run python -m unittest eval.test_eval
"""
import csv
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from eval import client, run, scoring

PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
                    "0000000d49444154789c6360000002000001e221bc330000000049454e44ae426082")


def task(answer, answer_type, **extra):
    return {"task_id": "t-000001", "image": "images/t.png", "question": "Q?", "answer": answer,
            "answer_type": answer_type, "question_type": "demo.q", **extra}


class ParseTest(unittest.TestCase):
    def test_takes_last_marker_and_strips_decoration(self):
        text = "First I thought FINAL ANSWER: 3\nbut no.\n**FINAL ANSWER:** `Wed 10:15`."
        self.assertEqual(scoring.parse_final_answer(text), "Wed 10:15")

    def test_answer_on_next_line(self):
        self.assertEqual(scoring.parse_final_answer("Final answer:\n\n  L3, L4\n"), "L3, L4")

    def test_boxed(self):
        self.assertEqual(scoring.parse_final_answer(r"FINAL ANSWER: $\boxed{12.5}$"), "12.5")

    def test_missing(self):
        self.assertEqual(scoring.parse_final_answer("I think it is 7."), "")
        self.assertEqual(scoring.parse_final_answer(""), "")


class ScoreTest(unittest.TestCase):
    def test_integer(self):
        t = task(1250, "integer")
        self.assertTrue(scoring.score("1,250", t))
        self.assertTrue(scoring.score("1250 kW", t))
        self.assertFalse(scoring.score("1250.4", t))
        self.assertFalse(scoring.score("none", t))
        self.assertFalse(scoring.score("", t))

    def test_number_tolerances(self):
        self.assertTrue(scoring.score("R = 12.4 Ω", task(12.5, "number", tolerance_abs=0.1)))
        self.assertFalse(scoring.score("12.3", task(12.5, "number", tolerance_abs=0.1)))
        self.assertTrue(scoring.score("104", task(100.0, "number", tolerance_rel=0.05)))
        self.assertFalse(scoring.score("106", task(100.0, "number", tolerance_rel=0.05)))
        self.assertTrue(scoring.score("−3", task(-3, "number")))
        self.assertTrue(scoring.score("3/4", task(0.75, "number", tolerance_abs=0.001)))

    def test_label(self):
        self.assertTrue(scoring.score("pump house 2.", task("Pump House 2", "label")))
        self.assertTrue(scoring.score("wed 10:15", task("Wed 10:15", "label")))
        self.assertFalse(scoring.score("Wed 10:45", task("Wed 10:15", "label")))

    def test_multiple_choice(self):
        t = task("B", "multiple_choice", options=["10 Ω", "12 Ω", "15 Ω"])
        for good in ("B", "(b)", "B) 12 Ω", "12 Ω"):
            self.assertTrue(scoring.score(good, t), good)
        for bad in ("C", "Both", "10 Ω"):
            self.assertFalse(scoring.score(bad, t), bad)

    def test_sequence(self):
        t = task(["L3", "L4", "L7"], "sequence")
        self.assertTrue(scoring.score("L3, L4, and L7", t))
        self.assertTrue(scoring.score('["L3", "L4", "L7"]', t))
        self.assertFalse(scoring.score("L4, L3, L7", t))            # order counts by default
        self.assertTrue(scoring.score("L4, L3, L7", {**t, "ordered": False}))
        self.assertFalse(scoring.score("L3, L4", {**t, "ordered": False}))

    def test_ref_answer_cell(self):
        self.assertEqual(scoring.ref_answer_cell(["L3", "L4"]), '["L3", "L4"]')
        self.assertEqual(scoring.ref_answer_cell(12), "12")
        self.assertEqual(scoring.ref_answer_cell("Wed 10:15"), "Wed 10:15")


class ClientTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.img = Path(self.tmp.name) / "x.png"
        self.img.write_bytes(PNG)
        env = {"EVAL_CACHE_DIR": str(Path(self.tmp.name) / "cache"), "OPENROUTER_API_KEY": "test-key", "MOCK": ""}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_cache_key_changes_with_every_input(self):
        base = client.cache_key("m", "p", "h", client.SETTINGS)
        self.assertEqual(base, client.cache_key("m", "p", "h", dict(client.SETTINGS)))
        for other in (("m2", "p", "h", client.SETTINGS), ("m", "p2", "h", client.SETTINGS),
                      ("m", "p", "h2", client.SETTINGS), ("m", "p", "h", {**client.SETTINGS, "max_tokens": 1})):
            self.assertNotEqual(base, client.cache_key(*other))

    def test_second_call_comes_from_cache_and_no_secret_or_image_is_stored(self):
        good = {"choices": [{"finish_reason": "stop", "message": {"content": "FINAL ANSWER: 4"}}],
                "usage": {"cost": 0.004}}
        with mock.patch.object(client, "_post_with_retries", return_value=(good, [{"attempt": 1}])) as post:
            first = client.call("m", "prompt", self.img)
            second = client.call("m", "prompt", self.img)
        self.assertEqual(post.call_count, 1)
        self.assertFalse(first["cached"])
        self.assertTrue(second["cached"])
        self.assertEqual(client.reply(second)["text"], "FINAL ANSWER: 4")
        sent = post.call_args.args[0]
        self.assertEqual((sent["temperature"], sent["reasoning"], sent["max_tokens"]), (0, {"effort": "high"}, client.SETTINGS["max_tokens"]))
        stored = next((Path(self.tmp.name) / "cache").glob("*.json")).read_text()
        self.assertNotIn("test-key", stored)
        self.assertNotIn("base64", stored)

    def test_raw_log_drops_opaque_blobs_only(self):
        blob = "Zm9v" * 200
        rec = {"response": {"choices": [{"finish_reason": "stop", "message": {
            "content": "FINAL ANSWER: 4", "reasoning": "thought",
            "reasoning_details": [{"type": "reasoning.encrypted", "data": blob},
                                  {"type": "reasoning.text", "text": "thought", "signature": blob}]}}],
            "usage": {"cost": 0.004}}}
        safe = client.for_raw_log(rec)
        self.assertNotIn(blob, json.dumps(safe))
        self.assertEqual(safe["response"]["choices"][0]["message"]["reasoning_details"][0]["data"]["chars"], 800)
        self.assertEqual(client.reply(safe), client.reply(rec))
        self.assertEqual(safe["response"]["choices"][0]["message"]["reasoning_details"][1]["text"], "thought")
        self.assertIn(blob, json.dumps(rec))                     # the original is not modified

    def test_failed_call_is_not_cached(self):
        with mock.patch.object(client, "_post_with_retries", return_value=(None, [{"attempt": 1, "problem": "x"}])):
            rec = client.call("m", "prompt", self.img)
        self.assertEqual(rec["error"], "api_error")
        self.assertFalse(list((Path(self.tmp.name) / "cache").glob("*.json")))

    def test_retries_then_succeeds(self):
        good = {"choices": [{"finish_reason": "stop", "message": {"content": "ok"}}]}
        bad = {"error": {"code": 502, "message": "upstream"}}
        replies = iter([bad, good])

        class Resp:
            def __init__(self, body): self.body = body
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return json.dumps(self.body).encode()

        with mock.patch.object(client.urllib.request, "urlopen", side_effect=lambda *a, **k: Resp(next(replies))), \
                mock.patch.object(client.time, "sleep") as sleep:
            raw, attempts = client._post_with_retries({"model": "m"})
        self.assertEqual(raw, good)
        self.assertEqual(len(attempts), 2)
        self.assertEqual(sleep.call_count, 1)


class RunTest(unittest.TestCase):
    def test_mock_run_writes_a_complete_results_folder(self):
        with tempfile.TemporaryDirectory() as d:
            tasks_dir, out = Path(d) / "tasks", Path(d) / "results"
            (tasks_dir / "images").mkdir(parents=True)
            (tasks_dir / "images" / "t.png").write_bytes(PNG)
            tasks = [task("mock", "label"), {**task(["L3", "L4"], "sequence"), "task_id": "t-000002"}]
            (tasks_dir / "tasks.jsonl").write_text("\n".join(json.dumps(t) for t in tasks) + "\n")
            with mock.patch.dict(os.environ, {"MOCK": "1", "EVAL_CACHE_DIR": str(Path(d) / "cache")}):
                summary = run.evaluate(tasks_dir, out)
            with open(out / "responses.csv", newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(list(rows[0].keys()), run.COLUMNS)
            self.assertEqual(len(rows), 4)
            self.assertTrue(all(r["status"] == "ok" and r["finish_reason"] == "stop" and r["error"] == "" for r in rows))
            self.assertEqual([r["correct"] for r in rows], ["1", "1", "0", "0"])
            self.assertEqual(rows[2]["ref_answer"], '["L3", "L4"]')
            self.assertEqual(len(list((out / "raw").glob("*.json"))), 4)
            cfg = json.loads((out / "run_config.json").read_text())
            self.assertEqual((cfg["temperature"], cfg["max_tokens"]), (0, client.SETTINGS["max_tokens"]))
            self.assertIn("FINAL ANSWER", cfg["prompt_template"])
            self.assertEqual(summary["by_model"][client.MODELS[0]]["correct"], 1)


if __name__ == "__main__":
    unittest.main()
