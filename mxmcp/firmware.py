"""Firmware repository inspection shared by tools and tests."""
from __future__ import annotations

import os
import re
from pathlib import Path

FW_PREFIX = "STM32Cube_FW_"


def default_repository() -> Path:
    return Path(os.environ.get("MXMCP_FW_REPOSITORY")
                or os.path.expanduser("~/STM32Cube/Repository"))


def scan_repository(repo: Path | None = None) -> list[dict]:
    """Every ``STM32Cube_FW_<family>_V<version>`` directory with completeness.

    A package is *complete* when `package.xml` and `Drivers/` are present; the
    interrupted-download leftovers (only `Projects/`) still count as "present"
    for CubeMX's version resolver, which is why they must be reported.
    """
    repo = Path(repo or default_repository())
    rows: list[dict] = []
    if not repo.is_dir():
        return rows
    for d in sorted(repo.iterdir()):
        if not d.is_dir() or not d.name.startswith(FW_PREFIX):
            continue
        rest = d.name[len(FW_PREFIX):]
        m = re.match(r"^(?P<fam>.+?)_V(?P<ver>.+)$", rest)
        if not m:
            continue
        pkg = d / "package.xml"
        release = ""
        if pkg.is_file():
            txt = pkg.read_text(encoding="iso-8859-1", errors="replace")
            i = txt.find('Release="')
            if i >= 0:
                release = txt[i + 9: txt.find('"', i + 9)]
        rows.append({
            "family": m.group("fam"),
            "version": m.group("ver"),
            "path": str(d),
            "release": release,
            "complete": pkg.is_file() and (d / "Drivers").is_dir(),
            "entries": sorted(p.name for p in d.iterdir())[:12],
        })
    return rows


def packages_for(family: str, repo: Path | None = None) -> list[dict]:
    marker = family.replace("STM32", "")
    return [r for r in scan_repository(repo) if r["family"] == marker]
