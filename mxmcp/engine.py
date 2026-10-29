r"""CubeMX engine driver.

Two transports, both going through the *official* CLI so every feature behaves
exactly like the desktop application:

1. Batch mode  (`java -jar STM32CubeMX.exe -q <script>`)
   Deterministic, self-contained, but ~15 s cold start. Used for generation,
   saving and any operation that should not leak state between calls.

2. Interactive mode (`java -jar STM32CubeMX.exe -i`, stdin/stdout)
   Keeps one warm process; each command is terminated by a line `<n> OK` or
   `<n> KO` where `n` includes header lines that are filtered with the
   log4j `[INFO]/[WARN]/[ERROR]` prefix. Async plugin chatter can appear
   *between* commands, so a small settle window and a strict terminator regex
   are used. Used for read queries and small incremental edits.

Wire format facts (probe tools/probe_interactive4.py):
  * reply terminator: `^\s*\d+ (OK|KO)\s*$`
  * the prompt `MX> ` is printed without a trailing newline
  * `get <x>` prints the value first, then the terminator
  * an unknown command prints the group usage table, then `N KO`
"""
from __future__ import annotations

import queue
import re
import shutil
import subprocess
import threading
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

DEFAULT_ROOT = Path(r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX")
TERMINATOR = re.compile(r"^\s*(\d+)\s+(OK|KO)\s*$")
GLUED_TERMINATOR = re.compile(r"(?:^|(?<=\D))(\d+)\s+(OK|KO)\s*$")
LOG_LINE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3} \[")
LOG_STAMP = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}\s+")
LOG_LEVEL = re.compile(r"^\[(?:TRACE|DEBUG|INFO|WARN|ERROR|FATAL)\]\s*", re.I)
LOG_SITE = re.compile(r"^[\w$.]+:\d+\s+-\s+")


def strip_log_prefix(line: str) -> str:
    """Reduce a log4j record to its message.

    `2026-..-.. 08:15:01,123 [INFO] IP:1953 - USART2 | BaudRate = 115200`
    becomes `USART2 | BaudRate = 115200`, which is what the command services put
    on the wire when they answer through the logger instead of stdout.
    """
    text = LOG_STAMP.sub("", line.strip(), count=1)
    text = LOG_LEVEL.sub("", text, count=1)
    return LOG_SITE.sub("", text, count=1)


class EngineError(RuntimeError):
    pass


def _decode(raw: bytes) -> str:
    return raw.decode("utf-8", "replace").rstrip("\r\n")


def is_noise(line: str) -> bool:
    s = line.strip()
    if not s:
        return True
    if LOG_LINE.match(s):
        return True
    if s.startswith("log4j user configuration file not found"):
        return True
    if s.startswith("Configure log4j with default settings"):
        return True
    if re.match(r"^\d+ : Invalid condition id", s):
        return True
    if s.startswith("MX> "):
        # prompt prefixed to a real payload line, keep the payload
        return False
    if s == "MX>":
        return True
    return False


def strip_prompt(line: str) -> str:
    """Remove the `MX> ` prompt from a line.

    CubeMX prints the prompt without a trailing newline, so depending on the
    write flushing it can appear at the start of a payload line (`MX> PC13: X`)
    or as a bare `MX>` followed by a newline.
    """
    if line.startswith("MX> "):
        return line[4:]
    if line == "MX>":
        return ""
    if line.startswith("MX>"):
        return line[3:]
    return line


@dataclass
class CommandResult:
    command: str
    status: str            # "OK" | "KO"
    payload: str           # payload text (lines before the terminator)
    raw: str               # everything received, filtered
    seconds: float
    hung: bool = False     # no terminator arrived before the deadline
    log: str = ""          # log4j lines emitted by the command (keep_log=True)

    @property
    def ok(self) -> bool:
        return self.status == "OK"

    def lines(self) -> list[str]:
        return [l for l in self.payload.splitlines() if l.strip()]


class Session:
    """A warm `-i` process."""

    def __init__(self, root: Path | str = DEFAULT_ROOT, workdir: Path | str | None = None,
                 startup_timeout: float = 120.0, settle: float = 0.35,
                 java: str | None = None) -> None:
        self.root = Path(root)
        self.workdir = Path(workdir or Path.cwd())
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.settle = settle
        self.java = java or str(self.root / "jre" / "bin" / "java.exe")
        if not Path(self.java).exists():
            self.java = shutil.which("java") or "java"
        self.exe = str(self.root / "STM32CubeMX.exe")
        self._q: queue.Queue[str | None] = queue.Queue()
        self._all: list[str] = []
        self._lock = threading.Lock()
        self._closed = False
        self._start(startup_timeout)

    # --------------------------------------------------------------- process
    def _start(self, startup_timeout: float) -> None:
        self.proc = subprocess.Popen(
            [self.java, "-Djavax.net.ssl.trustStoreType=WINDOWS-ROOT",
             "-jar", self.exe, "-i"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, cwd=str(self.workdir), bufsize=0)
        threading.Thread(target=self._reader, daemon=True).start()
        deadline = time.time() + startup_timeout
        while time.time() < deadline:
            if any(l.startswith("MX>") for l in self._all):
                return
            time.sleep(0.2)
        raise EngineError(
            f"CubeMX engine did not reach the MX> prompt within {startup_timeout:.0f}s")

    def _reader(self) -> None:
        assert self.proc.stdout is not None
        for raw in self.proc.stdout:
            line = _decode(raw)
            self._all.append(line)
            self._q.put(line)
        self._q.put(None)

    @property
    def alive(self) -> bool:
        return not self._closed and self.proc.poll() is None

    # -------------------------------------------------------------- protocol
    def send(self, command: str, timeout: float = 600.0,
             keep_log: bool = False) -> CommandResult:
        """Run one command and frame its reply.

        Some services (dma/gic/MMT/…) answer through log4j INFO lines instead of
        stdout; with keep_log those lines are collected separately so the caller
        still sees the data while `payload` stays clean.
        """
        if not self.alive:
            raise EngineError("engine process is not running")
        with self._lock:
            # drain leftover async chatter
            while True:
                try:
                    self._q.get_nowait()
                except queue.Empty:
                    break
            t0 = time.time()
            assert self.proc.stdin is not None
            self.proc.stdin.write((command + "\n").encode("utf-8"))
            self.proc.stdin.flush()
            payload: list[str] = []
            raw: list[str] = []
            logged: list[str] = []
            status = None
            deadline = t0 + timeout
            while time.time() < deadline:
                try:
                    line = self._q.get(timeout=0.25)
                except queue.Empty:
                    if self.proc.poll() is not None:
                        break
                    continue
                if line is None:
                    break
                line = strip_prompt(line)
                # A reply that prints nothing (set pin, set mode, config saveas)
                # leaves the prompt alone on its line; the next reply then starts
                # with the prompt glued to the payload ("MX> PC13: GPIO").
                if line.startswith("MX>"):
                    line = line[3:]
                if LOG_LINE.match(line.strip()):
                    # some services (dma/gic/MMT/…) answer through log4j lines
                    if keep_log:
                        logged.append(strip_log_prefix(line))
                    continue
                m = TERMINATOR.match(line)
                if not m:
                    # Some services print their reply and the terminator on the
                    # same line ("No DebugSysTickNo DebugSysTick0 OK"), so a
                    # line-anchored match alone would never end the frame.
                    m = GLUED_TERMINATOR.search(line)
                    if m:
                        head = line[: m.start()].rstrip()
                        if head:
                            raw.append(head)
                            payload.append(head)
                if m:
                    status = m.group(2)
                    break
                if is_noise(line):
                    continue
                raw.append(line)
                payload.append(line)
            if status is None:
                # A command that never answers leaves the interpreter busy: a
                # following command would be queued behind it and everything
                # afterwards would time out. Kill the engine so the next call
                # starts a clean one; the caller reloads the .ioc.
                hung = True
                self._mark_dead()
            else:
                hung = False
            return CommandResult(command=command,
                                 status=status or "KO",
                                 payload="\n".join(payload),
                                 raw="\n".join(raw),
                                 log="\n".join(logged),
                                 seconds=time.time() - t0,
                                 hung=hung)

    def _mark_dead(self) -> None:
        try:
            if self.proc.poll() is None:
                self.proc.kill()
                self.proc.wait(timeout=15)
        except Exception:  # noqa: BLE001
            pass

    def send_many(self, commands: Iterable[str], timeout: float = 600.0) -> list[CommandResult]:
        return [self.send(c, timeout=timeout) for c in commands if c.strip()]

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            if self.proc.poll() is None and self.proc.stdin:
                self.proc.stdin.write(b"exit\n")
                self.proc.stdin.flush()
                self.proc.wait(timeout=20)
        except Exception:  # noqa: BLE001
            pass
        finally:
            if self.proc.poll() is None:
                self.proc.kill()


def run_batch(root: Path | str, workdir: Path | str, commands: list[str],
              timeout: float = 900.0, java: str | None = None) -> tuple[int, str]:
    """Run `-q` with a script file; returns (returncode, filtered transcript)."""
    root = Path(root)
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    script = workdir / "mx_commands.txt"
    script.write_text("\n".join(commands) + "\nexit\n", encoding="ascii", errors="replace")
    exe = str(root / "STM32CubeMX.exe")
    java = java or str(root / "jre" / "bin" / "java.exe")
    if not Path(java).exists():
        java = shutil.which("java") or "java"
    log = workdir / "mx_console.log"
    with log.open("wb") as fh:
        proc = subprocess.Popen([java, "-Djavax.net.ssl.trustStoreType=WINDOWS-ROOT",
                                 "-jar", exe, "-q", str(script)],
                                stdout=fh, stderr=subprocess.STDOUT, cwd=str(workdir))
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=30)
    text = log.read_text(encoding="utf-8", errors="replace")
    lines = [l for l in text.splitlines() if not is_noise(l)]
    # drop echoed script lines
    out = []
    cmdset = set(commands)
    for l in lines:
        if l.strip() in cmdset:
            continue
        if "Cube IDE services" in l:
            continue
        out.append(l)
    return proc.returncode, "\n".join(out)
