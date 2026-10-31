"""Probe the CMSIS-Pack component commands and inspect resulting .ioc."""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from mxmcp.engine import Session  # noqa: E402


def main() -> int:
    wd = pathlib.Path("probe/pack2").resolve()
    wd.mkdir(parents=True, exist_ok=True)
    s = Session(workdir=wd)
    cmds = [
        "get version",
        "load STM32F103C8Tx",
        "pack status",
        "pack status " + str(wd / "pack_status.json"),
        "pack validate",
        "project path " + str(wd),
        "project name PackEx",
        "config saveas base.ioc",
    ]
    for cmd in cmds:
        r = s.send(cmd, timeout=300)
        print(f"[{r.status}] {r.seconds:6.1f}s  {cmd}")
        if r.payload:
            print("   " + r.payload.replace("\n", "\n   ")[:700])
    s.close()
    for p in wd.rglob("*"):
        if p.is_file():
            print("file:", p.relative_to(wd), p.stat().st_size)
    return 0


if __name__ == "__main__":
    sys.exit(main())
