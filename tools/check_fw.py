"""Enumerate which installed firmware packages are complete.

CubeMX resolves a package by looking for `package.xml` (+ Drivers/) in
`~/STM32Cube/Repository/STM32Cube_FW_<family>_V<version>`. Directories that only
hold `Projects/` (left over from a failed/interrupted download) force the engine
into an interactive download prompt, which is fatal in headless mode.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path(sys.argv[1] if len(sys.argv) > 1 else
            os.path.expanduser("~/STM32Cube/Repository"))


def main() -> int:
    rows = []
    for d in sorted(REPO.iterdir()):
        if not d.is_dir() or not d.name.startswith("STM32Cube_FW_"):
            continue
        marker = d.name[len("STM32Cube_FW_"):].split("_V")[0]
        version = d.name.split("_V")[-1]
        pkg = d / "package.xml"
        has_drivers = (d / "Drivers").is_dir()
        release = ""
        if pkg.is_file():
            try:
                txt = pkg.read_text(encoding="iso-8859-1", errors="replace")
                i = txt.find('Release="')
                if i >= 0:
                    release = txt[i + 9: txt.find('"', i + 9)]
            except OSError:
                pass
        rows.append((marker, version, pkg.is_file(), has_drivers, release,
                     len([p for p in d.iterdir()])))
    print(f"{'family':8s} {'version':10s} pkg drivers release   entries")
    for r in rows:
        print(f"{r[0]:8s} {r[1]:10s} {str(r[2]):5s} {str(r[3]):7s} {r[4]:9s} {r[5]}")
    ok = [f"{r[0]}_V{r[1]}" for r in rows if r[2] and r[3]]
    print("\ncomplete:", ", ".join(ok) or "none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
