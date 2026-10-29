"""Discover how CubeMX enables a middleware/RToS component headlessly.

`add mw` (argc=5) and `set mode <IP> "<mode>"` are the two candidates; the RTOS
row only exists after the component is integrated, and CubeMX drops unknown
`FREERTOS.*` keys on load, so this must be solved before rtos_* writes persist.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from mxmcp.engine import Session  # noqa: E402

PROBES = [
    "get mcu peripherals",
    "get modes FREERTOS",
    "get available modes FREERTOS",
    "get mapped modes FREERTOS",
    "add mw",
    "add mw FREERTOS CMSIS_V2",
    "set mode FREERTOS CMSIS_V2",
    'set mode FREERTOS "CMSIS_V2"',
    "get modes FREERTOS",
    "get pinout",
]


def main() -> int:
    wd = pathlib.Path("build/mw")
    wd.mkdir(parents=True, exist_ok=True)
    s = Session(workdir=wd)
    print("load:", s.send("load STM32F103C8Tx", timeout=240).status, flush=True)
    for cmd in PROBES:
        try:
            r = s.send(cmd, timeout=40, keep_log=True)
        except Exception as exc:  # noqa: BLE001
            print(f"{cmd:38s} ERROR {exc}", flush=True)
            break
        body = " | ".join(l for l in ((r.payload or "") + "\n" + (r.log or "")).splitlines()
                          if l.strip())
        print(f"### {cmd} [{r.status}] {body[:400]}", flush=True)
        if r.hung:
            s = Session(workdir=wd)
            s.send("load STM32F103C8Tx", timeout=240)
    s.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
