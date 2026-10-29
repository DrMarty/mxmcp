"""Third interactive probe: pin down the exact framing of a response.

Questions to answer:
  1. Is a successful command terminated by "<n> OK" on one line?
  2. Does `get version` print the value before "OK"?
  3. Are multi-line payloads (get pinout) flushed before the terminator?
  4. What happens for KO and for unknown commands?
  5. Does `set pin` produce a reply at all, and after how long?

Raw bytes are logged with timestamps so we can see partial-line behaviour.
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
    ("get version", 6),
    ("get modes USART1", 8),
    ("load STM32F103C8Tx", 20),
    ("set pin PC13 GPIO_Output", 8),
    ("get signal PC13.*", 6),
    ("get pinout", 6),
    ("bogus", 5),
    ("exit", 6),
]


def main() -> int:
    wd = Path(sys.argv[1] if len(sys.argv) > 1 else "probe/sess3").resolve()
    wd.mkdir(parents=True, exist_ok=True)
    log = (wd / "raw.log").open("wb")
    proc = subprocess.Popen([JAVA, "-jar", EXE, "-i"], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            cwd=str(wd), bufsize=0)
    start = time.time()

    def pump():
        while True:
            chunk = proc.stdout.read(1)  # type: ignore[union-attr]
            if not chunk:
                break
            log.write(f"[{time.time()-start:8.3f}] ".encode() + chunk)
            log.flush()

    threading.Thread(target=pump, daemon=True).start()
    for cmd, wait in STEPS:
        time.sleep(1)
        log.write(f"\n=== SEND {cmd!r} at {time.time()-start:.3f}\n".encode())
        log.flush()
        proc.stdin.write((cmd + "\n").encode())  # type: ignore[union-attr]
        proc.stdin.flush()  # type: ignore[union-attr]
        time.sleep(wait)
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
    log.close()
    raw = (wd / "raw.log").read_text(encoding="utf-8", errors="replace")
    # collapse the timestamp prefixes for readability
    out = []
    for line in raw.splitlines():
        if line.startswith("==="):
            out.append("\n" + line)
        elif "] " in line:
            out.append(line.split("] ", 1)[1])
        else:
            out.append(line)
    text = "".join(out)
    keep = [l for l in text.splitlines() if " [INFO]" not in l and " [WARN]" not in l]
    print("\n".join(keep)[-4000:])
    return 0


if __name__ == "__main__":
    sys.exit(main())
