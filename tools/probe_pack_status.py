"""Probe dumpStatus() behaviour of `pack status` without an argument."""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from mxmcp.engine import Session  # noqa: E402


def main() -> int:
    wd = pathlib.Path("probe/packstatus").resolve()
    wd.mkdir(parents=True, exist_ok=True)
    s = Session(workdir=wd)
    for cmd in ["load STM32F103C8Tx", "pack status", "pack status " + str(wd / "st.json")]:
        r = s.send(cmd, timeout=60)
        print(f"[{r.status}] {r.seconds:5.1f}s {cmd}")
        print("   payload:", repr(r.payload[:300]))
    s.close()
    for p in wd.rglob("*"):
        if p.is_file():
            print("file:", p.name, p.stat().st_size)
            if p.suffix == ".json":
                print(p.read_text(encoding="utf-8", errors="replace")[:800])
    return 0


if __name__ == "__main__":
    sys.exit(main())
