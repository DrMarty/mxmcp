"""Generation strategy test: live session state vs .ioc replay.

Observation: `project generate` completes in ~5 s after a project was configured
via CLI commands in the same session, but can stall when the same project is
loaded from a saved .ioc. This probe measures both paths with the same inputs.
"""
from __future__ import annotations

import pathlib
import shutil
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from mxmcp.engine import Session  # noqa: E402


def gen(s: Session, out: pathlib.Path, name: str, timeout: float = 60) -> tuple[str, float, int]:
    ok = True
    for c in ["project toolchain Makefile", f"project name {name}",
              f"project path {out}", "project generate"]:
        r = s.send(c, timeout=timeout)
        if r.status != "OK":
            return f"{c} -> {r.status}", r.seconds, 0
    n = len([x for x in out.rglob("*") if x.is_file()])
    return "OK", 0.0, n


def main() -> int:
    base = pathlib.Path("build/genstrat").resolve()
    # A: live session, clock pinned, then generate in the SAME session
    a = base / "a"
    shutil.rmtree(a, ignore_errors=True)
    a.mkdir(parents=True)
    s = Session(workdir=a)
    s.send("load STM32F103C8Tx", timeout=120)
    for c in ["set pin PC13 GPIO_Output", "set pin PA9 USART1_TX",
              "set pin PA10 USART1_RX", "set mode USART1 Asynchronous",
              "set ip parameters RCC IPParameters AHBFreq_Value,PLLMUL,PLLSourceVirtual,SYSCLKSource",
              "set ip parameters RCC AHBFreq_Value 72000000",
              "set ip parameters RCC PLLMUL RCC_PLL_MUL9",
              "set ip parameters RCC PLLSourceVirtual RCC_PLLSOURCE_HSE",
              "set ip parameters RCC SYSCLKSource RCC_SYSCLKSOURCE_PLLCLK",
              "clock resolution"]:
        s.send(c, timeout=120)
    st, sec, n = gen(s, a / "gen", "A")
    print(f"A live-session generate: {st} {sec:.1f}s files={n}", flush=True)
    s.send(f"config saveas {a / 'a.ioc'}", timeout=120)
    s.close()

    # B: fresh session, load that .ioc, generate
    b = base / "b"
    shutil.rmtree(b, ignore_errors=True)
    b.mkdir(parents=True)
    shutil.copyfile(a / "a.ioc", b / "b.ioc")
    s = Session(workdir=b)
    r = s.send(f"config load {b / 'b.ioc'}", timeout=180)
    print("B config load:", r.status, round(r.seconds, 1), flush=True)
    st, sec, n = gen(s, b / "gen", "B")
    print(f"B reloaded generate: {st} {sec:.1f}s files={n}", flush=True)
    s.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
