"""Tests for factory/export.py: the RL environment pack (envs.jsonl, verifier.py, sft.jsonl, MANIFEST.json).

    uv run python -m unittest tests.test_export
"""
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from factory.__main__ import main as cli
from factory.export import export_rl, load_verifier
from validate.run import validate_set

ROOT = Path(__file__).resolve().parents[1]
TOPO = [ROOT / "tasks" / f"pilot_topo_{m}" for m in ("crossings", "sunset", "flood")]


def run_cli(*argv) -> int:
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return cli(list(argv))


def jsonl(p: Path) -> list:
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


class ExampleFamilyExportTest(unittest.TestCase):
    """A tiny fixture built on the spot: the test-only example family, generated and validated."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.tasks = self.tmp / "tasks"
        self.assertEqual(run_cli("generate", "--family", "example", "--seeds", "0-5", "--out", str(self.tasks)), 0)
        validate_set(self.tasks, verbose=False)
        self.pack = self.tmp / "pack"
        self.assertEqual(run_cli("export", "--tasks", str(self.tasks), "--format", "rl", "--out", str(self.pack)), 0)
        self.v = load_verifier(self.pack / "verifier.py")
        self.envs = jsonl(self.pack / "envs.jsonl")

    def tearDown(self):
        self._tmp.cleanup()

    def test_pack_layout_and_manifest(self):
        for name in ("envs.jsonl", "sft.jsonl", "verifier.py", "MANIFEST.json"):
            self.assertTrue((self.pack / name).is_file(), name)
        man = json.loads((self.pack / "MANIFEST.json").read_text())
        self.assertGreater(len(self.envs), 0)
        self.assertEqual(man["environments"], len(self.envs))
        self.assertIn("public domain", man["license"]["terrain"])
        for rel, digest in man["sha256"].items():
            self.assertTrue((self.pack / rel).is_file(), rel)
        for e in self.envs:
            self.assertTrue((self.pack / e["image"]).is_file())
            self.assertTrue(e["prompt"].endswith("FINAL ANSWER: <your answer>"))

    def test_verifier_reference_one_wrong_zero(self):
        for e in self.envs:
            ref = e["reward_spec"]["reference"]
            wrong = next(x for x in ("A", "B", "C") if x != ref)
            self.assertEqual(self.v.reward(e, f"Let me look.\nFINAL ANSWER: {ref}"), 1.0)
            self.assertEqual(self.v.reward(e, f"FINAL ANSWER: {wrong}"), 0.0)
            self.assertEqual(self.v.reward(e, "no final line"), 0.0)

    def test_sft_solutions_verify(self):
        for row, e in zip(jsonl(self.pack / "sft.jsonl"), self.envs):
            self.assertEqual(row["env_id"], e["env_id"])
            self.assertEqual(self.v.reward(e, row["completion"]), 1.0)

    def test_verifier_runs_standalone(self):
        p = subprocess.run([sys.executable, "-I", str(self.pack / "verifier.py")], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_unvalidated_tasks_are_dropped(self):
        raw = self.tmp / "raw"
        run_cli("generate", "--family", "example", "--seeds", "0-2", "--out", str(raw))
        man = export_rl([raw], self.tmp / "pack2")
        self.assertEqual(man["environments"], 0)
        self.assertTrue(all(d["failed"] == ["not validated"] for d in man["dropped"]))


@unittest.skipUnless(all((d / "tasks.jsonl").is_file() for d in TOPO), "topo pilot sets not present")
class TopoPilotExportTest(unittest.TestCase):
    """The sample pack: the three topo pilots, with the per-mission worked solutions and shaping."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.pack = Path(cls._tmp.name) / "pack"
        export_rl(TOPO, cls.pack)
        cls.v = load_verifier(cls.pack / "verifier.py")
        cls.envs = {e["env_id"]: e for e in jsonl(cls.pack / "envs.jsonl")}
        cls.sft = {r["env_id"]: r for r in jsonl(cls.pack / "sft.jsonl")}

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_counts_and_regions(self):
        man = json.loads((self.pack / "MANIFEST.json").read_text())
        self.assertEqual(man["by_mission"], {"crossings": 10, "flood": 10, "sunset": 10})
        self.assertTrue(all(e["region"] for e in self.envs.values()))

    def test_reference_one_wrong_zero_and_solutions_verify(self):
        for tid, e in self.envs.items():
            ref = e["reward_spec"]["reference"]
            wrong = "C9" if isinstance(ref, str) else ref + 7
            self.assertEqual(self.v.reward(e, f"FINAL ANSWER: {ref}"), 1.0, tid)
            self.assertEqual(self.v.reward(e, f"FINAL ANSWER: {wrong}"), 0.0, tid)
            self.assertEqual(self.v.reward(e, self.sft[tid]["completion"]), 1.0, tid)
            self.assertIn("Step 1.", self.sft[tid]["completion"])

    def test_shaping(self):
        e = self.envs["topo-crossings-000000"]                     # reference 12; 10 = index contours left out
        self.assertEqual(self.v.reward(e, "FINAL ANSWER: 13"), 0.0)          # exact by default
        self.assertEqual(self.v.reward(e, "FINAL ANSWER: 13", shaped=True), 0.5)
        self.assertEqual(self.v.reward(e, "FINAL ANSWER: 10", shaped=True), 0.0)
        self.assertEqual(self.v.reward(e, "FINAL ANSWER: 12", shaped=True), 1.0)
        s = self.envs["topo-sunset-000000"]                        # reference 63, 4 min per uphill line
        self.assertEqual(self.v.reward(s, "FINAL ANSWER: 67", shaped=True), 0.5)
        self.assertEqual(self.v.reward(s, "FINAL ANSWER: -63", shaped=True), 0.5)
        self.assertEqual(self.v.reward(s, "FINAL ANSWER: 65", shaped=True), 0.0)
        f = self.envs["topo-flood-000000"]
        self.assertNotIn("shaping", f["reward_spec"])
        self.assertEqual(self.v.reward(f, "FINAL ANSWER: C1", shaped=True), 0.0)


if __name__ == "__main__":
    unittest.main()
