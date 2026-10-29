"""Test `pack enable` with TP_ADVANCED_MODE=on.

SharedServices.isAdvancedModeEnabled() reads env var / system property
TP_ADVANCED_MODE == "on"; QueryFilter uses it as `showPeripheralPack`, which
filters out ModelPeripheralPack entries (the per-MCU pseudo pack). With advanced
mode off, peripheral-level components can never be found -> KO.
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
    # (label, commands)
    ("adv_pack", ['pack enable STMicroelectronics "X-CUBE-BLE1/BlueNRG-MS" 7.1.0 "Wireless" "BlueNRG-MS/Controller"']),
    ("adv_hal", ['pack enable STMicroelectronics "HAL Drivers/STMicro_Driver" 0.0.1 "Device" "ADC/HAL"']),
    ("adv_pnp", ['pack enable STMicroelectronics "FP-SNS-STAIOTCFT" 1.0.0 "Application Library" "PnPL"']),
]


def run(label: str, extra: list[str]) -> None:
    wd = pathlib.Path(f"probe/packadv/{label}").resolve()
    shutil.rmtree(wd, ignore_errors=True)
    wd.mkdir(parents=True)
    script = wd / "s.txt"
    cmds = ["load STM32F103C8Tx"] + extra + [
        f"project path {wd}", "project name A", "config saveas a.ioc", "exit"]
    script.write_text("\n".join(cmds) + "\n")
    env = dict(os.environ, TP_ADVANCED_MODE="on")
    log = wd / "out.log"
    with log.open("wb") as fh:
        p = subprocess.Popen([JAVA, "-DTP_ADVANCED_MODE=on", "-jar", EXE, "-q", str(script)],
                             stdout=fh, stderr=subprocess.STDOUT, cwd=str(wd), env=env)
        p.wait(timeout=420)
    lines = [l for l in log.read_text(encoding="utf-8", errors="replace").splitlines()
             if " [INFO]" not in l and " [WARN]" not in l]
    i = next((k for k, l in enumerate(lines) if "pack enable" in l), 0)
    print(f"=== {label}")
    print("\n".join(lines[i:i + 12]))
    ioc = wd / "a" / "a.ioc"
    if ioc.exists():
        txt = ioc.read_text(encoding="iso-8859-1", errors="replace")
        print("third-party lines:",
              [l for l in txt.splitlines() if "ThirdParty" in l or "SH." in l][:8])


def main() -> int:
    for label, extra in ATTEMPTS:
        run(label, extra)
    return 0


if __name__ == "__main__":
    sys.exit(main())
