"""Redistribution policy check (runs in CI, exits non-zero on violation).

`mxmcp` is a client for STM32CubeMX, not a redistribution of it. Anything derived
from STMicroelectronics content must stay local:

  * the data pack built by `python -m mxmcp.bundle build`
  * the reverse-engineering extracts (`analysis/`, `_extract/`, `docs/javap/`)
  * the extracted FreeMarker/RTOS/CLI snapshot files under `mxmcp/data/`

This script fails if any of them is present in the tree, so a pull request cannot
accidentally publish ST-derived artifacts. See LICENSE "THIRD-PARTY NOTICES".
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# directories that must never be tracked
FORBIDDEN_DIRS = ["analysis", "_extract", "cls", "probe", "build",
                  "docs/javap", "docs/cli_help"]

# individual files / patterns that are ST-derived build artifacts
FORBIDDEN_FILES = [
    "mxmcp/data/cubemx-db.zip",
    "docs/rtos_apis.xml",
    "docs/cli_usage_tables.txt",
    "docs/cli_commands.tsv",
    "docs/cli_help.json",
    # verbatim javap / decompiled dumps of ST classes
    "docs/ThirdPartyCli.full.txt",
]

FORBIDDEN_GLOBS = ["docs/*.javap.txt"]

FORBIDDEN_SNAPSHOTS = [
    "mxmcp/data/config_model.json",
    "mxmcp/data/config_slim.json",
    "mxmcp/data/ip_modes.json",
    "mxmcp/data/middleware.json",
    "mxmcp/data/rtos_model.json",
    "mxmcp/data/cli_registry.json",
]

# files that may legitimately remain (small hand-written data)
ALLOWED = {"mxmcp/data/.gitkeep"}


def main() -> int:
    problems: list[str] = []
    for d in FORBIDDEN_DIRS:
        p = ROOT / d
        if p.exists() and any(p.rglob("*")):
            problems.append(f"directory present: {d}/ "
                            f"({sum(1 for _ in p.rglob('*'))} entries)")
    for f in FORBIDDEN_FILES + FORBIDDEN_SNAPSHOTS:
        p = ROOT / f
        if p.exists():
            problems.append(f"file present: {f}")
    for pattern in FORBIDDEN_GLOBS:
        for p in ROOT.glob(pattern):
            problems.append(f"file present: {p.relative_to(ROOT).as_posix()}")
    # a wheel must never carry a data pack
    for whl in (ROOT / "dist").glob("*.whl"):
        import zipfile
        with zipfile.ZipFile(whl) as z:
            for n in z.namelist():
                if n.endswith((".zip", ".i64", ".idb")):
                    problems.append(f"wheel {whl.name} contains {n}")
    if problems:
        print("redistribution policy violated:\n")
        for p in problems:
            print("  -", p)
        print("\nThese files are derived from STMicroelectronics content and must "
              "stay local.\nBuild them with `python -m mxmcp.bundle build` instead "
              "of committing them.\nSee LICENSE -> THIRD-PARTY NOTICES.")
        return 1
    print("compliance ok: no ST-derived artifacts in the tree")
    return 0


if __name__ == "__main__":
    sys.exit(main())
