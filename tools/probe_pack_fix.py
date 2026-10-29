"""Find which model/query gate rejects the BLE1 component.

SingleContextFilterController.queryModel() only does results.addAll(model.getComponents()).
So the filtering happens inside AbstractModel.getComponents() -> QueryFilter, and
the tree builder drops bundles unless exactly one child survives.

This probe walks AbstractModel/QueryFilter/ItemTree to see the exact entry point
that needs the component to be selectable, then re-tests with -resolve and with
the component that is alone in its bundle.
"""
from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess
import sys

JAVAP = r"C:\Program Files\Eclipse Adoptium\jdk-21.0.10.7-hotspot\bin\javap.exe"
TP = r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX\plugins\thirdparty.jar"
JAVA = r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX\jre\bin\java.exe"
EXE = r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX\STM32CubeMX.exe"


def javap(cls: str) -> str:
    p = subprocess.run([JAVAP, "-p", "-c", "-constants", "-cp", TP, cls],
                       capture_output=True, timeout=180)
    return p.stdout.decode("utf-8", "replace")


def run(label: str, cmds: list[str]) -> None:
    wd = pathlib.Path(f"probe/packfix/{label}").resolve()
    shutil.rmtree(wd, ignore_errors=True)
    wd.mkdir(parents=True)
    script = wd / "s.txt"
    script.write_text("\n".join(["load STM32F103C8Tx"] + cmds +
                                [f"project path {wd}", "project name F",
                                 "config saveas f.ioc", "exit"]) + "\n")
    env = dict(os.environ, TP_ADVANCED_MODE="on")
    with open(wd / "out.log", "wb") as fh:
        p = subprocess.Popen([JAVA, "-jar", EXE, "-q", str(script)],
                             stdout=fh, stderr=subprocess.STDOUT, cwd=str(wd), env=env)
        p.wait(timeout=300)
    lines = (wd / "out.log").read_text(encoding="utf-8", errors="replace").splitlines()
    keep = [l for l in lines if l.startswith("DBG") or l in ("OK", "KO")
            or "pack enable" in l or "pack validate" in l]
    idx = next((i for i, l in enumerate(keep) if "pack enable" in l), 0)
    print(f"=== {label}")
    print("\n".join(keep[idx:idx + 25]))
    ioc = wd / "f" / "f.ioc"
    if ioc.exists():
        txt = ioc.read_text(encoding="iso-8859-1", errors="replace")
        print("third-party:", [l for l in txt.splitlines() if "ThirdParty" in l][:5])


def main() -> int:
    # 1) understand getComponents()
    txt = javap("com.st.microxplorer.plugins.thirdparty.model.AbstractModel")
    open("docs/AbstractModel.javap.txt", "w", encoding="utf-8").write(txt)
    m = re.search(r"public java\.util\.List<[^>]+> getComponents\(\);(.*?)\n\n", txt, re.S)
    if m:
        print("=== AbstractModel.getComponents ===\n", m.group(1)[:1500])

    tests = [
        ("plain", ['pack enable STMicroelectronics "X-CUBE-BLE1/BlueNRG-MS" 7.1.0 "Wireless" "BlueNRG-MS/Controller"']),
        ("resolve", ['pack enable STMicroelectronics "X-CUBE-BLE1/BlueNRG-MS" 7.1.0 "Wireless" "BlueNRG-MS/Controller" -resolve']),
        ("utils", ['pack enable STMicroelectronics "X-CUBE-BLE1/BlueNRG-MS" 7.1.0 "Wireless" "BlueNRG-MS/Utils"']),
        ("seq", ['pack enable STMicroelectronics "X-CUBE-BLE1/BlueNRG-MS" 7.1.0 "Wireless" "BlueNRG-MS/Controller"',
                 'pack enable STMicroelectronics "X-CUBE-BLE1/BlueNRG-MS" 7.1.0 "Wireless" "BlueNRG-MS/Utils"',
                 "pack validate"]),
    ]
    for label, cmds in tests:
        run(label, cmds)
    return 0


if __name__ == "__main__":
    sys.exit(main())
