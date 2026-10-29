"""Framing probe: find exactly where one CLI reply ends and the prompt resumes.

The interactive path sometimes emits the prompt and the next payload on the same
physical line ("MX> PC13: GPIO"). We capture raw chunks with timestamps to build
a segmenter that recovers the boundary reliably.
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
    ("load STM32F103C8Tx", 12),
    ("set pin PC13 GPIO_Output", 3),
    ("get signal PC13.*", 2),
    ("get pinout", 2),
    ("get mapped modes .*", 2),
    ("exit", 3),
]


def main() -> int:
    wd = Path("probe/frame").resolve()
    wd.mkdir(parents=True, exist_ok=True)
    marks: list[float] = []
    events: list[tuple[float, bytes]] = []
    proc = subprocess.Popen([JAVA, "-jar", EXE, "-i"], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            cwd=str(wd), bufsize=0)
    t0 = time.time()

    def pump():
        while True:
            chunk = proc.stdout.read(512)  # type: ignore[union-attr]
            if not chunk:
                break
            events.append((time.time() - t0, chunk))

    threading.Thread(target=pump, daemon=True).start()
    time.sleep(12)
    for cmd, wait in STEPS:
        marks.append(time.time() - t0)
        proc.stdin.write((cmd + "\n").encode())  # type: ignore[union-attr]
        proc.stdin.flush()  # type: ignore[union-attr]
        time.sleep(wait)
    try:
        proc.wait(timeout=20)
    except subprocess.TimeoutExpired:
        proc.kill()

    # join into a single stream, then split at "MX>" occurrences
    buf = b""
    for ts, chunk in events:
        buf += chunk
    text = buf.decode("utf-8", "replace")
    print("=== prompt positions (char offsets) ===")
    pos = 0
    while True:
        i = text.find("MX>", pos)
        if i < 0:
            break
        start = text.rfind("\n", 0, i) + 1
        end = text.find("\n", i)
        line = text[start:end if end > 0 else len(text)]
        # strip log prefix noise on the same line
        if " [INFO]" in line or " [WARN]" in line:
            pos = i + 3
            continue
        print(f"@{i:7d} line={line[:90]!r}")
        pos = i + 3
    print("=== tail ===")
    print(text[-1200:])
    return 0


if __name__ == "__main__":
    sys.exit(main())
