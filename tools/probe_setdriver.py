"""Find the headless sequence that actually registers a middleware IP (FREERTOS).

`set mode FREERTOS CMSIS_V2` answers OK but leaves Mcu.IPn unchanged, so the
RTOS row never exists. Candidates: `setDriver`, `set ip driver`, mode with a
different root, or the third-party component path (`add mw`).
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from mxmcp.engine import Session  # noqa: E402

SEQ = [
    ("setDriver FREERTOS CMSIS_V2", "get mcu peripherals"),
    ("setDriver FREERTOS CMSIS_V2", "get ip parameters FREERTOS IPParameters"),
    ("set mode FREERTOS CMSIS_V2", "get ip parameters FREERTOS IPParameters"),
    ("set mode FREERTOS CMSIS_V1", "get ip parameters FREERTOS IPParameters"),
    ("set ip parameters FREERTOS IPParameters Tasks01",
     "get ip parameters FREERTOS IPParameters"),
    ("project toolchain Makefile", "config saveext project_ext.ioc"),
]


def main() -> int:
    wd = pathlib.Path("build/mw2")
    wd.mkdir(parents=True, exist_ok=True)
    s = Session(workdir=wd)
    print("load:", s.send("load STM32F103C8Tx", timeout=240).status, flush=True)
    print("setDriver usage:", s.send("setDriver", timeout=30).payload[:300], flush=True)
    for setcmd, check in SEQ:
        try:
            r1 = s.send(setcmd, timeout=40, keep_log=True)
            r2 = s.send(check, timeout=40, keep_log=True)
        except Exception as exc:  # noqa: BLE001
            print(f"{setcmd} ERROR {exc}", flush=True)
            break
        print(f"### {setcmd} [{r1.status}] log={(r1.log or '')[:120]}", flush=True)
        print(f"    {check} [{r2.status}] -> "
              f"{((r2.payload or '') + ' ' + (r2.log or '')).strip()[:200]}", flush=True)
        if r1.hung or r2.hung:
            s = Session(workdir=wd)
            s.send("load STM32F103C8Tx", timeout=240)
    print("pinout has FREERTOS ip?:",
          "FREERTOS" in s.send("get mcu peripherals", timeout=60).payload, flush=True)
    s.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
