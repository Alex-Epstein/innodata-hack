"""Checks for the topo family.   uv run python -m unittest gen.topo.test_topo"""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from gen import topo


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


class TopoFamily(unittest.TestCase):
    def test_every_template_and_difficulty_builds_and_two_solvers_agree(self):
        with tempfile.TemporaryDirectory() as tmp:
            for template in topo.TEMPLATES:
                for difficulty in (1, 2, 3):
                    task = topo.build(3, template, difficulty, Path(tmp))
                    data = json.loads((Path(tmp) / task["data"]).read_text(encoding="utf-8"))
                    self.assertEqual(topo.solve_independent(data, template), task["answer"], task["task_id"])
                    self.assertEqual(data["task_id"], task["task_id"])
                    self.assertTrue(task["steps"] and task["overlay"] and task["layout"]["probes"])
                    self.assertTrue(topo.REFERENCES[template])

    def test_same_seed_gives_the_same_bytes_and_answer(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            for template in topo.TEMPLATES:
                one, two = topo.build(11, template, 3, Path(a)), topo.build(11, template, 3, Path(b))
                self.assertEqual(one["answer"], two["answer"])
                self.assertEqual(one["question"], two["question"])
                for rel in (one["image"], one["data"]):
                    self.assertEqual(sha(Path(a) / rel), sha(Path(b) / rel), rel)

    def test_different_seeds_give_different_maps(self):
        with tempfile.TemporaryDirectory() as tmp:
            hashes = {sha(Path(tmp) / topo.build(s, "flood", 3, Path(tmp))["image"]) for s in range(4)}
            self.assertEqual(len(hashes), 4)

    def test_sunset_answer_follows_the_stated_rule(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = topo.build(5, "sunset", 3, Path(tmp))
            s = task["steps"]
            m = json.loads((Path(tmp) / task["data"]).read_text(encoding="utf-8"))["data"]["mission"]
            walk = m["flat_walk_min"] + m["minutes_per_uphill_contour"] * s["uphill_crossings"]
            self.assertEqual(task["answer"], (m["sunset_min"] - m["now_min"]) - walk)
            self.assertEqual(len(task["overlay"]["crossings"]), s["uphill_crossings"] + s["downhill_crossings"])

    def test_flood_has_exactly_one_camp_on_the_water_route(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = topo.build(5, "flood", 3, Path(tmp))
            camps = task["steps"]["camps"]
            self.assertEqual(len(camps), 6)
            self.assertEqual([c["camp"] for c in camps if c["flooded"]], [task["answer"]])
            self.assertTrue(all(c["distance_to_water_route_m"] >= 250 for c in camps if not c["flooded"]))

    def test_tiles_match_their_checksums(self):
        tiles = Path(topo.real.TILES)
        for line in (tiles / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
            digest, name = line.split()
            self.assertEqual(sha(tiles / name.lstrip("*")), digest, name)

    def test_unknown_template_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                topo.build(1, "nope", 3, Path(tmp))


if __name__ == "__main__":
    unittest.main()
