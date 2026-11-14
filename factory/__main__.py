"""The one command line for the pipeline (docs/ARCHITECTURE.md E7). See factory/README.md.

    uv run python -m factory list
    uv run python -m factory generate --family topo --template flood --difficulty 3 --seeds 0-9 --out tasks/pilot1
    uv run python -m factory validate --tasks tasks/pilot1 [--drop-invalid] [--blind-results results/extra/blind]
    uv run python -m factory eval     --tasks tasks/pilot1 --out results/pilot1
    uv run python -m factory rebuild  --tasks tasks/final [--out /out/rebuilt]
    uv run python -m factory fresh    --seed 7 [--family F --template T --difficulty D] [--out /tmp/fresh] [--show]
    uv run python -m factory export   --tasks tasks/pilot_topo_flood [--tasks ...] --format rl --out product/sample_pack
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path

from factory import registry
from factory.render import sha256_file
from factory.tasks import build_task, is_reject, load_tasks, parse_seeds, write_tasks

DEFAULT_DIFFICULTY = 3


# ---------------------------------------------------------------------------------------------- terminal output
class Style:
    def __init__(self):
        on = os.environ.get("FORCE_COLOR") or (sys.stdout.isatty() and not os.environ.get("NO_COLOR"))
        self.on = bool(on)

    def _c(self, code, s):
        return f"\033[{code}m{s}\033[0m" if self.on else s

    def ok(self, s): return self._c("32", s)
    def bad(self, s): return self._c("31", s)
    def dim(self, s): return self._c("2", s)
    def bold(self, s): return self._c("1", s)
    def cyan(self, s): return self._c("36", s)


S = Style()
TICK, CROSS = "✓", "✗"


def _err(e: BaseException) -> str:
    return traceback.format_exception_only(type(e), e)[-1].strip()


def _pick(names: str | None, available: list[str], what: str) -> list[str]:
    if not names or names == "all":
        return list(available)
    picked = [n.strip() for n in names.split(",") if n.strip()]
    unknown = [n for n in picked if n not in available]
    if unknown:
        raise SystemExit(f"unknown {what} {', '.join(unknown)} (available: {', '.join(available) or 'none'})")
    return picked


# ---------------------------------------------------------------------------------------------- list
def cmd_list(a) -> int:
    fams = registry.discover()
    if not fams:
        print("no working families under gen/")
    for name, m in fams.items():
        tag = "  (test only)" if getattr(m, "TEST_ONLY", False) else ""
        print(f"{name:<10} {m.VERSION:<18} templates: {', '.join(m.TEMPLATES)}{tag}")
    return 0


# ---------------------------------------------------------------------------------------------- generate
def cmd_generate(a) -> int:
    fams = registry.discover()
    families = _pick(a.family, registry.demo_families(), "family") if a.family in (None, "all") \
        else _pick(a.family, list(fams), "family")
    seeds = parse_seeds(a.seeds)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    old = load_tasks(out) if (out / "tasks.jsonl").exists() else []
    kept, rejected, errors, attempted = [], [], [], 0
    for fname in families:
        fam = fams[fname]
        for template in _pick(a.template, list(fam.TEMPLATES), f"template of {fname}"):
            for seed in seeds:
                attempted += 1
                tid = f"{fname}-{template}-{seed:06d}"
                try:
                    rec = build_task(fam, seed, template, a.difficulty, out)
                except Exception as e:
                    entry = {"task_id": tid, "family": fname, "template": template, "seed": seed,
                             "difficulty": a.difficulty, "reason": str(e) if is_reject(fam, e) else _err(e)}
                    (rejected if is_reject(fam, e) else errors).append(entry)
                    print(f"{'reject' if is_reject(fam, e) else 'ERROR '} {tid}: {entry['reason']}")
                    continue
                kept.append(rec)
                print(f"kept   {rec['task_id']}")

    new_ids = {r["task_id"] for r in kept}
    if a.append:
        records = [r for r in old if r["task_id"] not in new_ids] + kept
    else:
        records = kept
        for r in old:                                   # files of tasks this run no longer lists
            if r["task_id"] not in new_ids:
                for rel in (r.get("image"), r.get("data"), f"layout/{r['task_id']}.json"):
                    if rel and (out / rel).is_file():
                        (out / rel).unlink()
    write_tasks(out, records)
    log = {"families": {f: fams[f].VERSION for f in families}, "template": a.template or "all",
           "difficulty": a.difficulty, "seeds": a.seeds, "attempted": attempted,
           "rejected_count": len(rejected), "error_count": len(errors), "kept": len(kept),
           "rejected": rejected, "errors": errors}
    log_path = out / "generation_log.json"
    if a.append and log_path.exists():
        prev = json.loads(log_path.read_text(encoding="utf-8"))
        log = {**log, "attempted": prev.get("attempted", 0) + attempted,
               "rejected_count": prev.get("rejected_count", 0) + len(rejected),
               "error_count": prev.get("error_count", 0) + len(errors),
               "kept": len(records), "rejected": prev.get("rejected", []) + rejected,
               "errors": prev.get("errors", []) + errors, "runs": prev.get("runs", 1) + 1}
    log_path.write_text(json.dumps(log, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{attempted} attempted, {len(rejected)} rejected, {len(errors)} errors, {len(kept)} kept "
          f"-> {out / 'tasks.jsonl'}")
    return 1 if errors else 0


# ---------------------------------------------------------------------------------------------- validate
def cmd_validate(a) -> int:
    from validate.run import print_funnel, validate_set
    rep = validate_set(a.tasks, a.drop_invalid, a.blind_results, tuple(a.skip))
    print_funnel(rep)
    if a.drop_invalid:
        return 0 if rep["all_passed"] > 0 else 1
    return 0 if rep["all_passed"] == rep["checked"] else 1


# ---------------------------------------------------------------------------------------------- eval
def cmd_eval(a) -> int:
    from eval import run
    argv = ["--tasks", a.tasks, "--out", a.out, "--workers", str(a.workers)]
    for m in a.model or []:
        argv += ["--model", m]
    if a.blind:
        argv.append("--blind")
    return run.main(argv)


# ---------------------------------------------------------------------------------------------- rebuild
def cmd_rebuild(a) -> int:
    tasks_dir = Path(a.tasks)
    records = load_tasks(tasks_dir)
    fams = registry.discover()
    keep = Path(a.out) if a.out else None
    tmp_ctx = tempfile.TemporaryDirectory(prefix="rebuild-") if keep is None else contextlib.nullcontext(str(keep))
    rows, bad, rebuilt = [], 0, []
    with tmp_ctx as tmp:
        tmp = Path(tmp)
        for r in records:
            tid = r["task_id"]
            fam = fams.get(r.get("family"))
            if fam is None:
                rows.append((tid, "-", "-", "-", "-", f"family {r.get('family')!r} not available"))
                bad += 1
                continue
            template = r.get("template") or r["question_type"].split(".", 1)[1]
            try:
                new = build_task(fam, r["seed"], template, r["difficulty"], tmp)
            except Exception as e:
                rows.append((tid, "-", "-", "-", "-", f"build failed: {_err(e)}"))
                bad += 1
                continue
            same = {
                "png": sha256_file(tmp / new["image"]) == sha256_file(tasks_dir / r["image"]),
                "data": sha256_file(tmp / new["data"]) == sha256_file(tasks_dir / r["data"]),
                "question": new.get("question") == r.get("question"),
                "answer": new.get("answer") == r.get("answer"),
            }
            note = "" if r.get("generator_version") == fam.VERSION else \
                f"made by {r.get('generator_version')}, now {fam.VERSION}"
            ok = all(same.values())
            bad += not ok
            rows.append((tid, *(TICK if v else CROSS for v in same.values()), "identical" if ok else
                         ("MISMATCH " + note).strip()))
            if "checks" in r:
                new["checks"] = r["checks"]
            rebuilt.append(new)
        if keep is not None:
            write_tasks(keep, rebuilt)
    w = max([len(r[0]) for r in rows] + [7])
    print(f"{'task_id':<{w}}  png   data  question  answer  result")
    for tid, p, d, q, an, res in rows:
        color = S.ok if res == "identical" else S.bad
        print(f"{tid:<{w}}  {p:<5} {d:<5} {q:<9} {an:<7} {color(res)}")
    print(f"{len(records) - bad}/{len(records)} tasks rebuilt identical"
          + (f"; rebuilt set written to {keep}" if keep else ""))
    return 1 if bad else 0


# ---------------------------------------------------------------------------------------------- fresh (live demo)
def _default_out() -> Path:
    return Path(os.environ["OUT_DIR"]) / "fresh" if os.environ.get("OUT_DIR") else Path("/tmp/fresh")


def _ask_models(task: dict, out: Path, box: dict):
    """Runs in a background thread: both models on the fresh task, via eval (cached, retried)."""
    from concurrent.futures import ThreadPoolExecutor

    from eval import client, run
    try:
        with ThreadPoolExecutor(max_workers=len(client.MODELS)) as pool:
            box["rows"] = list(pool.map(lambda m: run.evaluate_one(m, task, out)[0], client.MODELS))
    except Exception as e:                              # FatalAPIError (no key), network, ...
        box["error"] = _err(e)


def cmd_fresh(a) -> int:
    fams = registry.discover()
    pause = (lambda: time.sleep(0.35)) if a.show else (lambda: None)
    if a.family:
        names = _pick(a.family, list(fams), "family")
    else:
        names = registry.demo_families()
    if not names:
        print("no working families under gen/", file=sys.stderr)
        return 2
    fname = names[a.seed % len(names)] if not a.family else names[0]
    fam = fams[fname]
    template = a.template or fam.TEMPLATES[(a.seed // len(names)) % len(fam.TEMPLATES)]
    if template not in fam.TEMPLATES:
        raise SystemExit(f"family {fname} has no template {template!r} (has {', '.join(fam.TEMPLATES)})")
    out = Path(a.out) if a.out else _default_out()
    out.mkdir(parents=True, exist_ok=True)

    print(S.bold(f"Fresh task · family {fname} · template {template} · difficulty {a.difficulty} · seed {a.seed}"))
    t0 = time.time()
    rec, seed = None, a.seed
    for seed in range(a.seed, a.seed + 50):
        try:
            rec = build_task(fam, seed, template, a.difficulty, out)
            break
        except Exception as e:
            if not is_reject(fam, e):
                raise
            print(S.dim(f"  seed {seed} rejected ({e}); trying seed {seed + 1}"))
            pause()
    if rec is None:
        print(S.bad("no fair task in 50 seeds"), file=sys.stderr)
        return 1
    write_tasks(out, [rec])                             # the eval thread reads the task from here

    box: dict = {}
    worker = threading.Thread(target=_ask_models, args=(rec, out, box), daemon=True)
    worker.start()                                      # the models think while we run the checks

    print(f"built {rec['task_id']} in {time.time() - t0:.1f}s")
    print(f"image:    {(out / rec['image']).resolve()}")
    print(f"data:     {(out / rec['data']).resolve()}")
    print(S.bold("question:"))
    for line in str(rec["question"]).splitlines() or [""]:
        print(f"  {line}")
    print()
    pause()

    print(S.bold("checks"))
    from validate.run import iter_checks
    results = []
    for name, ok, detail in iter_checks(out, rec):
        results.append((name, ok, detail))
        mark = S.ok(TICK) if ok else S.bad(CROSS)
        print(f"  {mark} {name:<24} {S.dim(detail)}")
        pause()
    rec["checks"] = {n: ok for n, ok, _ in results}
    write_tasks(out, [rec])
    all_ok = all(ok for _, ok, _ in results)
    print(f"  {sum(ok for _, ok, _ in results)}/{len(results)} checks pass"
          + ("" if all_ok else S.bad("  (task is NOT valid)")))
    print()

    if worker.is_alive():
        print(S.dim("waiting for the models..."))
    worker.join()
    print(S.bold("models") + S.dim(" (MOCK: canned replies, no API call)" if os.environ.get("MOCK") == "1" else ""))
    ref = rec["answer"] if isinstance(rec["answer"], str) else json.dumps(rec["answer"])
    if "error" in box:
        print(f"  {S.bad('models not called')}: {box['error']}")
    else:
        for row in box["rows"]:
            if row["error"]:
                verdict, shown = S.bad(f"incomplete ({row['error']})"), "-"
            else:
                verdict = S.ok(TICK) if row["correct"] == "1" else S.bad(CROSS)
                shown = row["parsed"] or "(no FINAL ANSWER line)"
            print(f"  {verdict} {row['model']:<28} answered {shown}")
            pause()
        # the results folder, written by eval exactly as for a task set (calls come from the cache)
        from eval import run
        with contextlib.redirect_stdout(io.StringIO()):
            try:
                run.evaluate(out, out / "results")
            except Exception as e:
                print(f"  could not write {out / 'results'}: {_err(e)}", file=sys.stderr)
    print(f"  {S.cyan('reference')}{' ' * 22}{ref}")
    print(S.dim(f"\ntask folder: {out.resolve()}  (tasks.jsonl, images/, data/, layout/, results/)"))
    return 0 if all_ok else 1


# ---------------------------------------------------------------------------------------------- main
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m factory", description="Visual Task Factory: generate, check, "
                                 "evaluate and rebuild visual reasoning tasks.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="list the working families and their templates").set_defaults(fn=cmd_list)

    g = sub.add_parser("generate", help="build tasks from seeds into a task folder")
    g.add_argument("--family", help="family name, comma list, or all (default: all except test-only)")
    g.add_argument("--template", help="template name, comma list, or all (default: all)")
    g.add_argument("--difficulty", type=int, default=DEFAULT_DIFFICULTY, help="1 easy, 2 medium, 3 hard")
    g.add_argument("--seeds", required=True, help="e.g. 0-9 or 1000-1009 or 1,4,9")
    g.add_argument("--out", required=True, help="task folder, e.g. tasks/pilot1")
    g.add_argument("--append", action="store_true", help="add to an existing tasks.jsonl instead of replacing it")
    g.set_defaults(fn=cmd_generate)

    v = sub.add_parser("validate", help="run every check, write checks into tasks.jsonl and validation_report.json")
    v.add_argument("--tasks", required=True)
    v.add_argument("--drop-invalid", action="store_true", help="keep only the tasks that pass every check")
    v.add_argument("--blind-results", help="blind eval folder (responses.csv) for the needs_image check")
    v.add_argument("--skip", action="append", default=[], help="skip a check by name (repeatable)")
    v.set_defaults(fn=cmd_validate)

    e = sub.add_parser("eval", help="evaluate both models on a task folder (delegates to eval.run)")
    e.add_argument("--tasks", required=True)
    e.add_argument("--out", required=True)
    e.add_argument("--model", action="append", help="repeatable; default: both evaluation models")
    e.add_argument("--workers", type=int, default=4)
    e.add_argument("--blind", action="store_true", help="send no image (write to results/extra/...)")
    e.set_defaults(fn=cmd_eval)

    r = sub.add_parser("rebuild", help="regenerate every task from its seed and compare hashes")
    r.add_argument("--tasks", required=True)
    r.add_argument("--out", help="keep the rebuilt set here (tasks.jsonl + files); default: a temp folder")
    r.set_defaults(fn=cmd_rebuild)

    f = sub.add_parser("fresh", help="live demo: build, check and score one new task")
    f.add_argument("--seed", type=int, required=True)
    f.add_argument("--family", help="default: picked from the seed")
    f.add_argument("--template", help="default: picked from the seed")
    f.add_argument("--difficulty", type=int, default=DEFAULT_DIFFICULTY)
    f.add_argument("--out", help="default: $OUT_DIR/fresh, else /tmp/fresh")
    f.add_argument("--show", action="store_true", help="short pauses between lines, for the stage")
    f.set_defaults(fn=cmd_fresh)

    from factory import export                          # product packs: RL envs + verifier + SFT (factory/export.py)
    export.add_parser(sub)

    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
