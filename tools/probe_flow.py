import os
import subprocess

JAVA = r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX\jre\bin\java.exe"
EXE = r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX\STM32CubeMX.exe"
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
WORK = os.path.join(ROOT, "build", "sessions")
os.makedirs(WORK, exist_ok=True)

# Full flow mirroring a real project: pins, mode, ip params, clock, project, generate
lines = [
    "load STM32F103C8Tx",
    "set pin PA9 USART1_TX",
    "set pin PA10 USART1_RX",
    "set mode USART1 Asynchronous",
    'set ip parameters USART1 BaudRate 115200',
    'set ip parameters RCC PLLState ENABLED',
    'set ip parameters RCC PLLMul PLLMUL9',
    'set ip parameters RCC HCLK 72000000',
    'get ip parameters RCC HCLK',
    "get mapped modes RCC",
    "get clock",
    "project name Demo",
    "project toolchain STM32CubeIDE",
    "project path " + os.path.join(WORK, "demo"),
    "project generate",
    "exit",
]
d = os.path.join(WORK, "flow1")
os.makedirs(d, exist_ok=True)
sp = os.path.join(d, "s.txt")
open(sp, "w", encoding="ascii").write("\n".join(lines) + "\n")
out = os.path.join(d, "out.log")
with open(out, "wb") as fh:
    p = subprocess.Popen([JAVA, "-Djavax.net.ssl.trustStoreType=WINDOWS-ROOT",
                          "-jar", EXE, "-q", sp],
                         stdout=fh, stderr=subprocess.STDOUT, cwd=d)
    p.wait(timeout=600)
txt = open(out, "rb").read().decode("utf-8", "replace")
keep = [l for l in txt.splitlines()
        if not (l[:4].isdigit() and " [" in l[:40]) and "Invalid condition id" not in l]
print("\n".join(keep[:400]))
