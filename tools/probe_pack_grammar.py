"""Brute-force the `pack enable` argument grammar against a real pack.

Each attempt runs in a fresh session (pack state is global to the engine), and
prints the packed status plus whether `Mcu.ThirdPartyNb` became non-zero in the
saved .ioc.
"""
from __future__ import annotations

import pathlib
import shutil
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from mxmcp.engine import Session  # noqa: E402

BASE = pathlib.Path("probe/packgram").resolve()

ATTEMPTS = [
    'pack enable STMicroelectronics "X-CUBE-BLE1/BlueNRG-MS" 7.1.0 "Wireless" "BlueNRG-MS/Controller"',
    'pack enable STMicroelectronics X-CUBE-BLE1 7.1.0 "Wireless" "BlueNRG-MS" "Controller"',
    'pack enable STMicroelectronics "X-CUBE-BLE1/BlueNRG-MS" 7.1.0 "Wireless" "BlueNRG-MS" "Controller"',
    'pack enable STMicroelectronics X-CUBE-BLE1 7.1.0 Wireless BlueNRG-MS',
    'pack enable STMicroelectronics X-CUBE-BLE1 7.1.0 Wireless Controller',
    'pack enable STMicroelectronics X-CUBE-BLE1/BlueNRG-MS 7.1.0 Wireless BlueNRG-MS/Controller',
    'pack enable STMicroelectronics "X-CUBE-BLE1" 7.1.0 "Wireless" "BlueNRG-MS"',
]


def attempt(idx: int, cmd: str) -> dict:
    wd = BASE / f"a{idx}"
    shutil.rmtree(wd, ignore_errors=True)
    wd.mkdir(parents=True, exist_ok=True)
    s = Session(workdir=wd)
    try:
        s.send("load STM32F103C8Tx", timeout=180)
        r = s.send(cmd, timeout=180)
        s.send(f"project path {wd}", timeout=60)
        s.send("project name G", timeout=60)
        s.send("config saveas g.ioc", timeout=60)
    finally:
        s.close()
    ioc = wd / "g" / "g.ioc"
    txt = ioc.read_text(encoding="iso-8859-1", errors="replace") if ioc.exists() else ""
    tp = [l for l in txt.splitlines() if l.startswith("Mcu.ThirdParty")]
    return {"cmd": cmd, "status": r.status, "payload": r.payload[:300], "third_party": tp}


def main() -> int:
    for i, cmd in enumerate(ATTEMPTS):
        res = attempt(i, cmd)
        print(f"[{res['status']}] {cmd}")
        if res["payload"]:
            print("   ", res["payload"].replace("\n", "\n    "))
        if res["third_party"]:
            print("   THIRD PARTY:", res["third_party"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
