"""Find the image families: every package gen/<name>/ that implements contracts/FAMILY.md.

A family that fails to import or misses part of the interface is skipped with one warning on stderr, so a
teammate's half-built family never breaks the golden path for everyone else.
"""
from __future__ import annotations

import importlib
import sys
import traceback
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parent.parent
GEN = ROOT / "gen"
REQUIRED = ("FAMILY", "VERSION", "TEMPLATES", "REFERENCES", "build", "solve_independent", "RejectSeed")

_cache: dict[str, ModuleType] | None = None
_warnings: list[str] = []


def _problems(mod: ModuleType) -> list[str]:
    out = [f"missing {name}" for name in REQUIRED if not hasattr(mod, name)]
    if out:
        return out
    if not isinstance(mod.FAMILY, str) or not mod.FAMILY:
        out.append("FAMILY is not a non-empty string")
    if not isinstance(mod.VERSION, str) or not mod.VERSION:
        out.append("VERSION is not a non-empty string")
    if not isinstance(mod.TEMPLATES, (list, tuple)) or not mod.TEMPLATES:
        out.append("TEMPLATES is not a non-empty list")
    if not isinstance(mod.REFERENCES, dict):
        out.append("REFERENCES is not a dict {template: [sources]}")
    if not callable(mod.build) or not callable(mod.solve_independent):
        out.append("build / solve_independent are not callable")
    if not (isinstance(mod.RejectSeed, type) and issubclass(mod.RejectSeed, Exception)):
        out.append("RejectSeed is not an Exception class")
    return out


def discover(refresh: bool = False, quiet: bool = False) -> dict[str, ModuleType]:
    """{FAMILY: module} for every working family under gen/, sorted by name."""
    global _cache
    if _cache is not None and not refresh:
        return _cache
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    found: dict[str, ModuleType] = {}
    _warnings.clear()
    for d in sorted(GEN.iterdir()) if GEN.is_dir() else []:
        if not d.is_dir() or d.name.startswith((".", "_")) or not (d / "__init__.py").exists():
            continue
        try:
            mod = importlib.import_module(f"gen.{d.name}")
        except Exception as e:                       # a broken family must not break the others
            last = traceback.format_exception_only(type(e), e)[-1].strip()
            _warnings.append(f"skipping family gen/{d.name}: import failed: {last}")
            continue
        problems = _problems(mod)
        if problems:
            _warnings.append(f"skipping family gen/{d.name}: does not follow contracts/FAMILY.md "
                             f"({'; '.join(problems)})")
            continue
        if mod.FAMILY in found:
            _warnings.append(f"skipping family gen/{d.name}: FAMILY {mod.FAMILY!r} already used by "
                             f"{found[mod.FAMILY].__name__}")
            continue
        found[mod.FAMILY] = mod
    if not quiet:
        for w in _warnings:
            print(f"WARNING: {w}", file=sys.stderr)
    _cache = dict(sorted(found.items()))
    return _cache


def warnings() -> list[str]:
    return list(_warnings)


def get(family: str) -> ModuleType:
    fams = discover()
    if family not in fams:
        known = ", ".join(fams) or "none"
        raise KeyError(f"unknown family {family!r} (working families: {known})")
    return fams[family]


def demo_families() -> list[str]:
    """Families to pick from when none is named: everything except test-only ones (TEST_ONLY = True),
    unless that leaves nothing."""
    fams = discover()
    real = [f for f, m in fams.items() if not getattr(m, "TEST_ONLY", False)]
    return real or list(fams)
