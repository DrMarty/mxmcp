"""Explore the b4 (Cclass/bundle) and b5 (Cgroup/Csub) argument interpretation.

findComponent() walks bundle children, so the Cclass argument may need to be the
bundle name (what the GUI shows as the bundle node) with the class passed
separately. These attempts test that mapping against the built-in HAL pack.
"""
from __future__ import annotations

import pathlib
import shutil
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from mxmcp.engine import Session  # noqa: E402

ATTEMPTS = [
    'pack enable STMicroelectronics "HAL Drivers" 0.0.0 "STMicro_Driver" "ADC/HAL"',
    'pack enable STMicroelectronics "HAL Drivers" 0.0.0 "Device" "ADC/HAL"',
    'pack enable STMicroelectronics "STMicro_Driver" 0.0.0 "Device" "ADC/HAL"',
    'pack enable STMicroelectronics "HAL Drivers" 0.0.0 "STMicro_Driver" "ADC" "HAL"',
    'pack enable STMicroelectronics "HAL Drivers" 0.0.0 "ADC" "HAL"',
    'pack enable STMicroelectronics "HAL Drivers/STMicro_Driver" 0.0.0 "ADC" "HAL"',
]


def main() -> int:
    for i, cmd in enumerate(ATTEMPTS):
        wd = pathlib.Path(f"probe/pack9/{i}").resolve()
        shutil.rmtree(wd, ignore_errors=True)
        wd.mkdir(parents=True)
        s = Session(workdir=wd)
        try:
            s.send("load STM32F103C8Tx", timeout=180)
            r = s.send(cmd, timeout=120)
            s.send(f"project path {wd}", timeout=60)
            s.send("project name X", timeout=60)
            s.send("config saveas x.ioc", timeout=60)
        finally:
            s.close()
        ioc = wd / "x" / "x.ioc"
        tp = []
        if ioc.exists():
            tp = [l for l in ioc.read_text(encoding="iso-8859-1", errors="replace").splitlines()
                  if "ThirdParty" in l]
        print(f"[{r.status}] {cmd}  -> {tp}  {r.payload[:120]!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
