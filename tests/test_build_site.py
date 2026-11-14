"""scripts/build-site: the Beat the AI data export (grid, map frame, overlay, model answers) and the texture alignment."""
import base64
import importlib.machinery
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
_loader = importlib.machinery.SourceFileLoader("build_site", str(ROOT / "scripts" / "build-site"))
_spec = importlib.util.spec_from_loader("build_site", _loader)
build_site = importlib.util.module_from_spec(_spec)
_loader.exec_module(build_site)

TOPO = ("tasks/pilot_topo_flood", "results/pilot_topo_flood")
MISSIONS = ("results/spikes/missions_v2/tasks", "results/spikes/missions_v2/results")


@unittest.skipUnless((ROOT / TOPO[0] / "tasks.jsonl").exists(), "pilot tasks not present")
class BuildSiteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name)
        args = ["--tasks", TOPO[0], "--results", TOPO[1], "--out", str(cls.out), "--quiet",
                "--only", "topo-flood-00000[01]|topoM-los-000201"]
        if (ROOT / MISSIONS[0] / "tasks.jsonl").exists():
            args += ["--tasks", MISSIONS[0], "--results", MISSIONS[1]]
        build_site.main(args)
        cls.index = json.loads((cls.out / "data" / "index.json").read_text())

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def task(self, tid):
        return json.loads((self.out / "data" / f"{tid}.json").read_text())

    def test_index_and_files(self):
        ids = [t["task_id"] for t in self.index["tasks"]]
        self.assertIn("topo-flood-000000", ids)
        self.assertIn(self.index["featured"], ids)
        for tid in ids:
            for f in (f"data/{tid}.json", f"data/{tid}.js", f"img/{tid}.png", f"img/{tid}_thumb.jpg"):
                self.assertTrue((self.out / f).exists(), f)

    def test_image_is_the_exact_png_the_models_saw(self):
        self.assertEqual((self.out / "img/topo-flood-000000.png").read_bytes(),
                         (ROOT / TOPO[0] / "images/topo-flood-000000.png").read_bytes())

    def test_answers_come_from_the_task_and_responses_csv(self):
        t = self.task("topo-flood-000000")
        rec = json.loads((ROOT / TOPO[0] / "tasks.jsonl").read_text().splitlines()[0])
        self.assertEqual(t["answer"], rec["answer"])
        self.assertEqual(set(t["models"]), {"haiku", "luna"})
        import csv
        rows = [r for r in csv.DictReader((ROOT / TOPO[1] / "responses.csv").open()) if r["task_id"] == "topo-flood-000000"]
        for r in rows:
            slot = "haiku" if "haiku" in r["model"] else "luna"
            self.assertEqual(t["models"][slot]["parsed"], r["parsed"])
            self.assertEqual(t["models"][slot]["correct"], r["correct"] == "1")

    def test_grid_decodes_and_matches_the_family_terrain(self):
        t = self.task("topo-flood-000000")
        g = t["grid"]
        z = np.frombuffer(base64.b64decode(g["data"]), dtype="<u2").reshape(g["rows"], g["cols"])
        z = g["zmin"] + z / 65535 * (g["zmax"] - g["zmin"])
        self.assertAlmostEqual(g["cols"] / g["rows"], t["extent_m"][0] / t["extent_m"][1], places=1)
        # the dam's elevation from the exported grid equals the generator's own number (steps.dam_elev_m)
        dam = next(p for p in t["scene"]["points"] if p["name"] == "D")
        gx, gy = dam["g"]
        c0, r0 = int(gx), int(gy)
        fc, fr = gx - c0, gy - r0
        v = (z[r0, c0] * (1 - fc) * (1 - fr) + z[r0, c0 + 1] * fc * (1 - fr) + z[r0 + 1, c0] * (1 - fc) * fr
             + z[r0 + 1, c0 + 1] * fc * fr)
        self.assertAlmostEqual(v, t["steps"]["dam_elev_m"], delta=1.5)

    def test_texture_is_the_map_frame(self):
        """Every marker, placed by its grid coordinates on the cropped texture, lands on its magenta symbol."""
        for tid in [t["task_id"] for t in self.index["tasks"] if t["has3d"]]:
            t = self.task(tid)
            tex = Image.open(self.out / t["texture"]).convert("RGB")
            W, H = tex.size
            f = t["frame_px"]
            self.assertAlmostEqual((f[2] - f[0]) / (f[3] - f[1]), t["extent_m"][0] / t["extent_m"][1], places=2)
            for p in t["scene"]["points"]:
                if p["role"] not in ("dam", "camp", "start", "end", "spotter", "hiker"):
                    continue
                x = p["g"][0] / (t["grid"]["cols"] - 1) * W
                y = p["g"][1] / (t["grid"]["rows"] - 1) * H
                best = min(sum(abs(a - b) for a, b in zip(tex.getpixel((int(x) + dx, int(y) + dy)), (176, 18, 126)))
                           for dx in (-2, 0, 2) for dy in (-2, 0, 2))
                if tid.startswith("topo-"):                   # gen/topo draws every mark as a magenta symbol
                    self.assertLess(best, 90, f"{tid} {p['name']}")

    def test_overlay_geometry(self):
        t = self.task("topo-flood-000000")
        water = next(p for p in t["scene"]["paths"] if p["role"] == "water")
        self.assertGreater(len(water["pts"]), 10)
        self.assertEqual(t["scene"]["target"], t["answer"])
        tgt = next(p for p in t["scene"]["points"] if p["name"] == t["answer"])
        end = water["pts"][-1]
        cell = t["extent_m"][0] / (t["grid"]["cols"] - 1)
        gap = min(np.hypot(q[0] - tgt["g"][0], q[1] - tgt["g"][1]) for q in water["pts"]) * cell
        self.assertLess(gap, 40.5)                           # the flooded camp is within the generator's 40 m hit radius
        self.assertTrue(0 <= end[0] <= t["grid"]["cols"] - 1 and 0 <= end[1] <= t["grid"]["rows"] - 1)

    def test_label_options(self):
        t = self.task("topo-flood-000000")
        self.assertEqual(t["options"], ["C1", "C2", "C3", "C4", "C5", "C6"])
        if (self.out / "data/topoM-los-000201.json").exists():
            los = self.task("topoM-los-000201")
            self.assertEqual(los["options"], ["yes", "no"])
            self.assertIn("los", los["scene"])


if __name__ == "__main__":
    unittest.main()
