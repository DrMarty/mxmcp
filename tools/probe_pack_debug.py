"""Find why `pack enable` returns KO.

The KO carries no message in the CLI transcript, but the plugin logs through
log4j to stdout with [INFO]; raw lines were filtered by the engine. This probe
re-runs one attempt and prints *every* line around the command.
"""
from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import time

JAVA = r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX\jre\bin\java.exe"
EXE = r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX\STM32CubeMX.exe"

CMDS = [
    "load STM32N657X0HxQ",
    'pack enable STMicroelectronics "X-CUBE-BLE1/BlueNRG-MS" 7.1.0 "Wireless" "BlueNRG-MS/Controller"',
    "pack status",
    "exit",
]


def main() -> int:
    wd = pathlib.Path("probe/packdbg").resolve()
    shutil.rmtree(wd, ignore_errors=True)
    wd.mkdir(parents=True, exist_ok=True)
    script = wd / "s.txt"
    script.write_text("\n".join(CMDS) + "\n")
    log = wd / "out.log"
    with log.open("wb") as fh:
        p = subprocess.Popen([JAVA, "-jar", EXE, "-q", str(script)],
                             stdout=fh, stderr=subprocess.STDOUT, cwd=str(wd))
        p.wait(timeout=420)
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
    start = next((i for i, l in enumerate(lines) if "pack enable" in l), 0)
    print("\n".join(lines[start - 3:start + 60]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
