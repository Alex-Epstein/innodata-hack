#!/usr/bin/env python3
"""Fill the organizers' 5-slide template (docs/organizer/presentation-template.pptx) from the result files.

    python3 slides/build.py --team "Team Name" --members "A · B · C · D"     -> slides/presentation.pptx

Every number on the slides is read here from tasks/final, results/final, results/pilot_topo_*, the 2.0.0 pilot
numbers recorded in gen/topo/README.md and results/extra/fewshot/summary.md. Standard library only.
"""
import argparse
import csv
import json
import re
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "docs" / "organizer" / "presentation-template.pptx"
OUT = ROOT / "slides" / "presentation.pptx"
HAIKU, LUNA = "anthropic/claude-haiku-5.5", "openai/gpt-6-luna"
csv.field_size_limit(10 ** 9)


def rows_of(folder):
    return list(csv.DictReader(open(ROOT / folder / "responses.csv", encoding="utf-8")))


def right(rows, model):
    mine = [r for r in rows if r["model"] == model]
    return sum(r["correct"] == "1" for r in mine), len(mine)


def facts():
    f = {}
    tasks = [json.loads(l) for l in (ROOT / "tasks/final/tasks.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    log = json.loads((ROOT / "tasks/final/generation_log.json").read_text(encoding="utf-8"))
    rep = json.loads((ROOT / "tasks/final/validation_report.json").read_text(encoding="utf-8"))
    rows = rows_of("results/final")
    tot = json.loads((ROOT / "results/final/summary.json").read_text(encoding="utf-8"))["totals"]
    f["n"], f["attempted"], f["rejected"] = len(tasks), log["attempted"], log["rejected_count"]
    f["valid"], f["checked"] = rep["all_passed"], rep["checked"]
    f["haiku"], f["luna"] = "%d/%d" % right(rows, HAIKU), "%d/%d" % right(rows, LUNA)
    f["replies"] = len(rows)
    f["complete"] = sum(r["finish_reason"] == "stop" and not r["error"] for r in rows)
    f["retried"], f["incomplete"] = tot["retried_calls"], tot["incomplete"]
    got = {(r["model"], r["task_id"]): r for r in rows}
    both_wrong = [t for t in tasks if all(got[(m, t["task_id"])]["correct"] != "1" for m in (HAIKU, LUNA))]
    pick = lambda kind: next(t for t in both_wrong if t["question_type"].endswith(kind))
    for key, kind in (("flood", "flood"), ("cross", "crossings")):
        t = pick(kind)
        f[key] = (t["task_id"], t["answer"], got[(HAIKU, t["task_id"])]["parsed"], got[(LUNA, t["task_id"])]["parsed"])
    pilot = [r for m in ("crossings", "sunset", "flood") for r in rows_of(f"results/pilot_topo_{m}")]
    f["pilot_haiku"], f["pilot_luna"] = "%d/%d" % right(pilot, HAIKU), "%d/%d" % right(pilot, LUNA)
    few = (ROOT / "results/extra/fewshot/summary.md").read_text(encoding="utf-8")
    m = re.search(r"got (\d+/\d+) right zero-shot and (\d+/\d+) right with two examples", few)
    f["zero"], f["two"] = m.group(1), m.group(2)
    f["hand"] = (ROOT / "results/human/hand_check.md").exists()
    return f


def texts(f, team, members):
    hand = f"We submitted {f['n']} hand-checked tasks." if f["hand"] else f"We submitted {f['n']} tasks (hand check in progress)."
    fl, cr = f["flood"], f["cross"]
    return {
        "[Project name]": "The Map vs the Mountain",
        "[Team name] · [Coding Task Factory or Visual Task Factory]": f"{team} · Visual Task Factory",
        "[Member names]": members,
        "Our pipeline generates [kind of task] to test whether a model can [specific capability].":
            "Our pipeline generates map-reading missions on real USGS terrain to test whether a model can trace a "
            "path through clutter: along a trail across contour lines, or downhill with the water.",
        "[One concrete example of where that capability matters.]":
            "Where it matters: a hiking assistant shown a photo of a trail map and asked \"will I make it before dark?\"",
        "[Repository and commit, or structured data and seed]":
            "A seed and real elevation data (USGS 3DEP, public domain, bundled). The seed fixes the place, the trail "
            "or the dam and camps, and every label. Same seed, same task, byte for byte.",
        "[Two or three steps from input to finished task]":
            "Write the data JSON → draw the USGS-style map from that file → compute the answer from it two "
            "independent ways → 7 automatic checks. A seed that fails is rejected with its reason.",
        "[One example of a meaningful change in behavior or reasoning]":
            "Three reasoning chains: count every contour line a trail crosses · count only the uphill ones and beat "
            "the sunset (Naismith's rule) · follow the water downhill to one of six camps.",
        "[Put the command or demo entry point here, then switch to the running pipeline.]":
            f"Play it: alex-epstein.github.io/innodata-hack  ·  Exemplar {fl[0]}: reference {fl[1]}, Haiku {fl[2]}, "
            f"Luna {fl[3]}  ·  Then a judge picks a seed: docker run --rm -e OPENROUTER_API_KEY -v \"$(pwd)/out:/out\" "
            "visual-task-factory fresh --seed N",
        "CODING": "VISUAL · THE REPORTED TASKS",
        "[__ of __ unedited packages passed every check.] [Model ID] achieved [__ successful graded rollouts / __ "
        "completed graded rollouts]. Per task, resolve@5 was [x/5]. [One failure and what the logs showed.]":
            f"{f['valid']} of {f['attempted']} generated tasks were valid ({f['rejected']} seeds rejected). {hand} On "
            f"those tasks, {HAIKU} answered {f['haiku']} correctly and {LUNA} answered {f['luna']} correctly. "
            f"{f['complete']} of {f['replies']} replies complete: {f['retried']} retries, {f['incomplete']} cut-offs or errors.",
        "VISUAL": "VISUAL · THE CHANGE AFTER THE PILOT",
        "[__ of __ generated tasks were valid. We submitted 10 hand-checked tasks.] On those tasks, [model A] answered "
        "[__ / __] correctly and [model B] answered [__ / __] correctly. [One change after the pilot and what happened.]":
            "A reviewer flagged our dashed red trail, so we redrew it solid magenta and kept the end markers off "
            f"contour lines. The 30 pilot tasks stayed hard (Haiku {f['pilot_haiku']}, Luna {f['pilot_luna']}), so "
            "the misses are reasoning, not legibility.",
        "[One conclusion supported by a task or run you just showed.]":
            "They read, but they can't trace. Labels and arithmetic come out right; the count along the trail does "
            f"not ({cr[0]}: reference {cr[1]}, Haiku {cr[2]}, Luna {cr[3]}).",
        "[What still fails, needs a manual step, or remains incomplete?]":
            f"{f['n']} reported tasks is a small sample. Trails and camps are drawn for the exercise on real terrain "
            "from 4 bundled regions. The flood answer is a 1-in-6 choice.",
        "[What would you change or measure next, and why?]":
            f"Two worked examples in the prompt did not help ({f['zero']} right without, {f['two']} with). Next: "
            "fine-tune on the verified step-by-step solutions and measure on held-out regions.",
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--team", required=True)
    ap.add_argument("--members", required=True)
    a = ap.parse_args()
    swap = texts(facts(), a.team, a.members)
    used = set()
    with zipfile.ZipFile(TEMPLATE) as src, zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            if re.fullmatch(r"ppt/slides/slide\d+\.xml", item.filename):
                xml = data.decode("utf-8")
                for old, new in swap.items():
                    tag = f"<a:t>{escape(old)}</a:t>"
                    if tag in xml:
                        xml = xml.replace(tag, f"<a:t>{escape(new)}</a:t>")
                        used.add(old)
                data = xml.encode("utf-8")
            elif re.fullmatch(r"ppt/notesSlides/notesSlide\d+\.xml", item.filename):
                data = re.sub(r"<a:t>[^<]*</a:t>", "<a:t></a:t>", data.decode("utf-8")).encode("utf-8")   # template instructions
            dst.writestr(item, data)
    missing = [k for k in swap if k not in used]
    if missing:
        raise SystemExit("template text not found: " + "; ".join(m[:50] for m in missing))
    print(f"{OUT}: {len(used)} texts filled")


if __name__ == "__main__":
    main()
