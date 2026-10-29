"""Probe `add mw` and `import` families: user middleware and ioc import.

`add mw name root_dir mode_file config_file template_dir` registers a user
middleware (the classic "custom middleware" feature). `import config <file>`
imports another ioc into the current project; `import openioc` is its GUI twin.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from mxmcp.engine import Session  # noqa: E402


def main() -> int:
    wd = pathlib.Path("probe/mw").resolve()
    wd.mkdir(parents=True, exist_ok=True)
    s = Session(workdir=wd)
    steps = [
        "add mw",
        "import openioc",
        "import set",
        "import try",
        "import get",
        "list ipdependencies",
        "get bsp status",
        "tooltip log",
        "clock resolution",
        "check mcus",
        "csv pinout " + str(wd / "pinout.csv"),
        "loadboard NUCLEO-F103RB",
    ]
    for c in steps:
        r = s.send(c, timeout=180)
        print(f"[{r.status}] {r.seconds:5.1f}s {c}")
        if r.payload:
            print("   " + r.payload.replace("\n", "\n   ")[:500])
    s.close()
    print("csv exists:", (wd / "pinout.csv").exists())
    return 0


if __name__ == "__main__":
    sys.exit(main())
