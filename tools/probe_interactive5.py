"""Fifth probe: does bare `help` inside `-i` show the group's sub-commands?

Rationale: `get` printed "This is the help" + full table once; later `get ...`
without valid sub-command printed a sub-command-only usage table. We need to
know which input form yields the detailed sub-command help so the MCP server
can expose real parameter documentation instead of guessing.
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
    ("get", 6),
    ("get ?", 6),
    ("get help", 6),
    ("help", 6),
    ("nvic", 6),
    ("NVIC ?", 6),
    ("dma ?", 6),
    ("pack ?", 6),
    ("clock ?", 6),
    ("pinout ?", 6),
    ("exit", 5),
]


def main() -> int:
    wd = Path(sys.argv[1] if len(sys.argv) > 1 else "probe/sess5").resolve()
    wd.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen([JAVA, "-jar", EXE, "-i"], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            cwd=str(wd), bufsize=0)
    buf: list[str] = []

    def pump():
        for raw in proc.stdout:  # type: ignore[union-attr]
            buf.append(raw.decode("utf-8", "replace").rstrip("\r\n"))

    threading.Thread(target=pump, daemon=True).start()
    time.sleep(15)
    transcript = []
    for cmd, wait in STEPS:
        buf.clear()
        proc.stdin.write((cmd + "\n").encode())  # type: ignore[union-attr]
        proc.stdin.flush()  # type: ignore[union-attr]
        time.sleep(wait)
        lines = [l for l in list(buf) if " [INFO]" not in l and " [WARN]" not in l
                 and " [ERROR]" not in l and "Invalid condition" not in l]
        transcript.append(f"\n=== {cmd!r}\n" + "\n".join(lines))
    try:
        proc.wait(timeout=20)
    except subprocess.TimeoutExpired:
        proc.kill()
    text = "\n".join(transcript)
    (wd / "transcript.txt").write_text(text, encoding="utf-8")
    print(text[:12000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
