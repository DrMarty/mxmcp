import os
import subprocess
import sys
import time

JAVA = r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX\jre\bin\java.exe"
EXE = r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX\STM32CubeMX.exe"
WORK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "probe")
WORK = os.path.abspath(WORK)
os.makedirs(WORK, exist_ok=True)
script = os.path.join(WORK, "p1.txt")
with open(script, "w", encoding="ascii") as fh:
    fh.write("help\nversion\nexit\n")
out = os.path.join(WORK, "help_out.txt")
with open(out, "wb") as fh:
    p = subprocess.Popen(
        [JAVA, "-Djavax.net.ssl.trustStoreType=WINDOWS-ROOT", "-jar", EXE,
         "-q", script],
        stdout=fh, stderr=subprocess.STDOUT, cwd=WORK)
    try:
        p.wait(timeout=240)
    except subprocess.TimeoutExpired:
        p.kill()
        print("TIMEOUT")
print("rc", p.returncode)
print(open(out, "rb").read().decode("utf-8", "replace")[:8000])
