import json
import os
import shutil
import subprocess
import sys
import time

JAVA = r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX\jre\bin\java.exe"
EXE = r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX\STM32CubeMX.exe"
HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.abspath(os.path.join(HERE, "..", "probe"))
os.makedirs(WORK, exist_ok=True)


def run(lines, name, timeout=420):
    script = os.path.join(WORK, name + ".txt")
    with open(script, "w", encoding="ascii") as fh:
        fh.write("\n".join(lines) + "\n")
    out = os.path.join(WORK, name + ".log")
    with open(out, "wb") as fh:
        p = subprocess.Popen([JAVA, "-Djavax.net.ssl.trustStoreType=WINDOWS-ROOT",
                              "-jar", EXE, "-q", script],
                             stdout=fh, stderr=subprocess.STDOUT, cwd=os.path.join(WORK, name))
        try:
            p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            p.kill()
            print(name, "TIMEOUT")
    txt = open(out, "rb").read().decode("utf-8", "replace")
    # strip log4j style lines
    keep = [l for l in txt.splitlines() if not (l[:4].isdigit() and " [" in l[:40])]
    print(f"===== {name} rc={p.returncode} lines={len(txt.splitlines())}")
    print("\n".join(keep[:200]))
    return txt


for n in ("s_load", "s_mcu", "s_cfg", "s_proj"):
    os.makedirs(os.path.join(WORK, n), exist_ok=True)

run(["get version", "load STM32F103C8Tx", "get name", "get version",
     "config save " + os.path.join(WORK, "s_load", "t1.ioc"), "exit"], "s_load")

run(["load STM32F103C8Tx",
     "get mcu name", "get mcu family", "get mcu pin", "get mcu",
     "get pin", "get ip", "list", "exit"], "s_mcu")

run(["load STM32F103C8Tx",
     "get config", "get pinout", "get ioc", "get core", "get clock",
     "exit"], "s_cfg")

run(["load STM32F103C8Tx",
     "project name T1", "project toolchain STM32CubeIDE",
     "project path " + os.path.join(WORK, "s_proj"),
     "get project name", "get project path",
     "project generate", "exit"], "s_proj")
