"""Run one pack-enable session with third-party debug logging enabled.

Writes ~/.stm32cubemx/log4j2.xml with pattern 'DBG %c{1}:%L - %m%n' so every
FilterController / QueryFilter decision becomes visible, then prints the DBG
lines around the command.
"""
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys

JAVA = r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX\jre\bin\java.exe"
EXE = r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX\STM32CubeMX.exe"

CMD = ('pack enable STMicroelectronics "X-CUBE-BLE1/BlueNRG-MS" 7.1.0 '
       '"Wireless" "BlueNRG-MS/Controller"')


def main() -> int:
    wd = pathlib.Path("probe/dbg1").resolve()
    shutil.rmtree(wd, ignore_errors=True)
    wd.mkdir(parents=True)
    cmds = ["load STM32F103C8Tx", CMD, "exit"]
    (wd / "s.txt").write_text("\n".join(cmds) + "\n")
    env = dict(os.environ, TP_ADVANCED_MODE="on")
    with open(wd / "out.log", "wb") as fh:
        p = subprocess.Popen([JAVA, "-jar", EXE, "-q", str(wd / "s.txt")],
                             stdout=fh, stderr=subprocess.STDOUT, cwd=str(wd), env=env)
        p.wait(timeout=300)
    lines = (wd / "out.log").read_text(encoding="utf-8", errors="replace").splitlines()
    dbg = [l for l in lines if l.startswith("DBG")]
    print("debug lines:", len(dbg))
    print("\n".join(dbg[:80]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
