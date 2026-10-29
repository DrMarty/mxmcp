"""Probe `pack enable` on an mcufinder X-CUBE pack and inspect the saved .ioc.

Everything runs in an isolated work dir. The CLI is known to call ST servers for
the pack metadata cache, so a generous timeout is used and failure reasons are
reported verbatim.
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from mxmcp.engine import Session  # noqa: E402


def main() -> int:
    wd = pathlib.Path("probe/pack3").resolve()
    wd.mkdir(parents=True, exist_ok=True)
    s = Session(workdir=wd)
    steps = [
        "load STM32F103C8Tx",
        'pack enable STMicroelectronics "X-CUBE-BLE1" 4.2.0 "Wireless" "Controller"',
        "pack validate",
        "project path " + str(wd),
        "project name Pk3",
        "config saveas pk3.ioc",
    ]
    for cmd in steps:
        r = s.send(cmd, timeout=240)
        print(f"[{r.status}] {r.seconds:6.1f}s  {cmd}")
        if r.payload:
            print("   " + r.payload.replace("\n", "\n   ")[:600])
    s.close()
    iocs = list(wd.rglob("*.ioc"))
    for ioc in iocs:
        print("IOC:", ioc.relative_to(wd))
        print(ioc.read_text(encoding="iso-8859-1", errors="replace")[:2000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
