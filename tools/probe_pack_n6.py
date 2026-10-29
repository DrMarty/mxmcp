"""Re-test pack enable on an N6 target (ble1 supports N6 in the pdsc condition)."""
from __future__ import annotations

import pathlib
import shutil
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from mxmcp.engine import Session  # noqa: E402


def main() -> int:
    wd = pathlib.Path("probe/pack6").resolve()
    shutil.rmtree(wd, ignore_errors=True)
    wd.mkdir(parents=True)
    s = Session(workdir=wd)
    steps = [
        "load STM32N657X0HxQ",
        "get mcu name",
        'pack enable STMicroelectronics "X-CUBE-BLE1/BlueNRG-MS" 7.1.0 "Wireless" "BlueNRG-MS/Controller"',
        "pack validate",
        "project path " + str(wd),
        "project name N6",
        "config saveas n6.ioc",
    ]
    for c in steps:
        r = s.send(c, timeout=300)
        print(f"[{r.status}] {r.seconds:5.1f}s {c}")
        if r.payload:
            print("   " + r.payload.replace("\n", "\n   ")[:600])
    s.close()
    ioc = wd / "n6" / "n6.ioc"
    if ioc.exists():
        txt = ioc.read_text(encoding="iso-8859-1", errors="replace")
        print("\n".join(l for l in txt.splitlines() if "ThirdParty" in l or "BLE" in l)[:1500])
    return 0


if __name__ == "__main__":
    sys.exit(main())
