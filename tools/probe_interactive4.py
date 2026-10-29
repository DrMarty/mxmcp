"""Clean framing capture for the CubeMX interactive CLI.

Writes every byte with a timestamp so we can reconstruct exact response
boundaries, then prints a filtered transcript (log lines removed) with
<SEND> and <RECV> separators.

Key questions:
  * is the terminal reply line exactly "<n> OK" / "<n> KO"?
  * does the payload of `get version` / `get pinout` precede it?
  * how long does `set pin` take to answer?
"""
from __future__ import annotations

import subprocess
import sys
import threading
import time
from pathlib import Path

JAVA = r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX\jre\bin\java.exe"
EXE = r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX\STM32CubeMX.exe"

STEPS = [
    ("get version", 5),
    ("load STM32F103C8Tx", 25),
    ("set pin PC13 GPIO_Output", 6),
    ("get signal PC13.*", 5),
    ("set mode USART1 Asynchronous", 5),
    ("nonsensecommand xyz", 5),
    ("exit", 5),
]


def main() -> int:
    wd = Path(sys.argv[1] if len(sys.argv) > 1 else "probe/sess4").resolve()
    wd.mkdir(parents=True, exist_ok=True)
    events: list[tuple[float, bytes]] = []
    log = (wd / "raw.log").open("wb")
    proc = subprocess.Popen([JAVA, "-jar", EXE, "-i"], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            cwd=str(wd), bufsize=0)
    t0 = time.time()

    def pump():
        while True:
            chunk = proc.stdout.read(4096)  # type: ignore[union-attr]
            if not chunk:
                break
            events.append((time.time() - t0, chunk))
            log.write(chunk)
            log.flush()

    threading.Thread(target=pump, daemon=True).start()
    sends: list[tuple[float, str]] = []
    for cmd, wait in STEPS:
        time.sleep(2)
        sends.append((time.time() - t0, cmd))
        proc.stdin.write((cmd + "\n").encode())  # type: ignore[union-attr]
        proc.stdin.flush()  # type: ignore[union-attr]
        time.sleep(wait)
    try:
        proc.wait(timeout=20)
    except subprocess.TimeoutExpired:
        proc.kill()
    log.close()

    # rebuild transcript with timestamps per line
    text_parts = []
    for ts, chunk in events:
        text_parts.append((ts, chunk.decode("utf-8", "replace")))
    lines: list[tuple[float, str]] = []
    for ts, txt in text_parts:
        for ln in txt.split("\n"):
            lines.append((ts, ln))
    out = []
    prev_ts = 0.0
    for ts, ln in lines:
        if "[INFO]" in ln or "[WARN]" in ln or "[ERROR]" in ln:
            continue
        for sts, cmd in sends:
            if ts >= sts > prev_ts:
                out.append(f"\n<<< SEND @{sts:.2f}s: {cmd}")
        prev_ts = ts
        if ln.strip():
            out.append(f"[{ts:7.2f}] {ln[:200]}")
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
