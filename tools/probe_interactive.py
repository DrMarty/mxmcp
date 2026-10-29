"""Persistent CubeMX CLI session probe.

Goal: verify that `java -jar STM32CubeMX.exe -i` exposes a usable line-oriented
protocol (prompt `MX>`, reply terminated by OK/KO) so the MCP server can keep one
warm process instead of paying the ~15 s cold start per call.

Also verifies the documented `-q <script>` + stdin hybrid is NOT needed.
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


class Session:
    def __init__(self, workdir: Path):
        self.q: queue.Queue[str] = queue.Queue()
        self.buf: list[str] = []
        self.workdir = workdir
        workdir.mkdir(parents=True, exist_ok=True)
        self.proc = subprocess.Popen(
            [JAVA, "-Djavax.net.ssl.trustStoreType=WINDOWS-ROOT", "-jar", EXE, "-i"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, cwd=str(workdir), bufsize=0)
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self) -> None:
        for raw in self.proc.stdout:  # type: ignore[union-attr]
            line = raw.decode("utf-8", "replace").rstrip("\r\n")
            self.buf.append(line)
            self.q.put(line)

    def send(self, cmd: str) -> list[str]:
        self.proc.stdin.write((cmd + "\n").encode())  # type: ignore[union-attr]
        self.proc.stdin.flush()  # type: ignore[union-attr]
        out = []
        deadline = time.time() + 120
        while time.time() < deadline:
            try:
                line = self.q.get(timeout=0.5)
            except queue.Empty:
                if self.proc.poll() is not None:
                    break
                continue
            out.append(line)
            if line.strip() in ("OK", "KO"):
                # a bare OK/KO terminates the response for one command
                break
            if line.strip().startswith("MX>") and out[-1].strip() == line.strip():
                break
        return out

    def wait_ready(self, timeout: float = 90) -> bool:
        end = time.time() + timeout
        while time.time() < end:
            joined = "\n".join(self.buf)
            if "MX>" in joined:
                return True
            time.sleep(0.2)
        return False

    def close(self) -> None:
        try:
            self.proc.stdin.write(b"exit\n")  # type: ignore[union-attr]
            self.proc.stdin.flush()  # type: ignore[union-attr]
        except Exception:
            pass
        try:
            self.proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            self.proc.kill()


if __name__ == "__main__":
    wd = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path("./probe/sess")
    t0 = time.time()
    s = Session(wd)
    ok = s.wait_ready()
    print(f"ready={ok} in {time.time()-t0:.1f}s")
    print("---- banner tail ----")
    print("\n".join(s.buf[-12:]))
    for cmd in ["get version", "load STM32F103C8Tx", "get mcu name", "exit"]:
        t = time.time()
        resp = s.send(cmd)
        print(f"==== {cmd}  ({time.time()-t:.2f}s)")
        print("\n".join(resp[-20:]))
    s.close()
