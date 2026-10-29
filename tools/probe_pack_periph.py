"""Probe pack enable using the per-MCU peripheral HAL components.

Pack status shows one component per peripheral HAL for the loaded MCU:
  STMicroelectronics:STM32F103C8Tx:0.0.0:STMicroelectronics:Peripheral::ADC:ADC1:HAL:0.0.0
i.e. vendor=STMicroelectronics, pack=STM32F103C8Tx, version=0.0.0,
class="Peripheral", group="", subgroup="ADC", variant="ADC1", api="HAL".

These are ModelPeripheralPack entries (visible only with TP_ADVANCED_MODE=on),
which is exactly the advanced-mode branch of QueryFilter.
"""
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys

JAVA = r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX\jre\bin\java.exe"
EXE = r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX\STM32CubeMX.exe"

ATTEMPTS = [
    ("per1", 'pack enable STMicroelectronics STM32F103C8Tx 0.0.0 "Peripheral" "ADC/ADC1"'),
    ("per2", 'pack enable STMicroelectronics STM32F103C8Tx 0.0.0 "Peripheral" "ADC" "ADC1"'),
    ("per3", 'pack enable STMicroelectronics STM32F103C8Tx 0.0.0 "Peripheral" "ADC/ADC1" "HAL"'),
    ("per4", 'pack enable STMicroelectronics STM32F103C8Tx 0.0.0 "Peripheral" "" "ADC"'),
]


def run(label: str, cmd: str) -> None:
    wd = pathlib.Path(f"probe/packper/{label}").resolve()
    shutil.rmtree(wd, ignore_errors=True)
    wd.mkdir(parents=True)
    (wd / "s.txt").write_text("\n".join(
        ["load STM32F103C8Tx", cmd, f"project path {wd}", "project name P",
         "config saveas p.ioc", "exit"]) + "\n")
    env = dict(os.environ, TP_ADVANCED_MODE="on")
    with open(wd / "out.log", "wb") as fh:
        p = subprocess.Popen([JAVA, "-jar", EXE, "-q", str(wd / "s.txt")],
                             stdout=fh, stderr=subprocess.STDOUT, cwd=str(wd), env=env)
        p.wait(timeout=300)
    lines = (wd / "out.log").read_text(encoding="utf-8", errors="replace").splitlines()
    sel = [l for l in lines if l.startswith("DBG") and ("Add filter" in l or "ThirdPartyCli" in l)]
    idx = next((i for i, l in enumerate(lines) if "pack enable" in l), 0)
    tail = lines[idx:idx + 3]
    ioc = wd / "p" / "p.ioc"
    tp = []
    if ioc.exists():
        tp = [l for l in ioc.read_text(encoding="iso-8859-1", errors="replace").splitlines()
              if "ThirdParty" in l]
    print(f"=== {label}: {cmd}")
    print("   result:", tail[:2], "| third-party:", tp)
    for l in sel[-8:]:
        print("   ", l[:160])


def main() -> int:
    for label, cmd in ATTEMPTS:
        run(label, cmd)
    return 0


if __name__ == "__main__":
    sys.exit(main())
