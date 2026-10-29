"""Second-generation interactive probe: understand the exact wire protocol.

Observed in probe 1: the reply is not simply "OK". CubeMX echoes token counts
and, when stdin is a pipe, it interleaves asynchronous log lines. We need to
know precisely where a response ends so the MCP engine can reliably frame it.
"""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

JAVA = r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX\jre\bin\java.exe"
EXE = r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX\STM32CubeMX.exe"


def main() -> int:
    wd = Path(sys.argv[1] if len(sys.argv) > 1 else "probe/sess2").resolve()
    wd.mkdir(parents=True, exist_ok=True)
    log = (wd / "raw.log").open("wb")
    proc = subprocess.Popen([JAVA, "-jar", EXE, "-i"], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            cwd=str(wd), bufsize=0)
    start = time.time()

    def pump():
        for raw in proc.stdout:  # type: ignore[union-attr]
            log.write(f"[{time.time()-start:8.3f}] ".encode() + raw)
            log.flush()

    threading.Thread(target=pump, daemon=True).start()
    time.sleep(20)
    for cmd in [b"get version\n", b"load STM32F103C8Tx\n",
                b"set pin PC13 GPIO_Output\n", b"get pinout\n",
                b"bogus command\n", b"exit\n"]:
        proc.stdin.write(cmd)  # type: ignore[union-attr]
        proc.stdin.flush()  # type: ignore[union-attr]
        time.sleep(8)
    try:
        proc.wait(timeout=60)
    except subprocess.TimeoutExpired:
        proc.kill()
    log.close()
    print((wd / "raw.log").read_text(encoding="utf-8", errors="replace")[-6000:])
    return 0


if __name__ == "__main__":
    sys.exit(main())
