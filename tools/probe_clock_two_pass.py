"""Test the reload-and-reapply clock strategy directly.

Observation: applying the RCC parameter sequence once on a brand-new project
leaves PLLCLK at the default; applying the same sequence to a project *saved and
reloaded* converges to 72 MHz. This probe validates that as a tool strategy.
"""
from __future__ import annotations

import pathlib
import shutil
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from mxmcp.store import ProjectManager  # noqa: E402

PARAMS = [
    ("PLLMUL", "RCC_PLL_MUL9"),
    ("PLLSourceVirtual", "RCC_PLLSOURCE_HSE"),
    ("SYSCLKSource", "RCC_SYSCLKSOURCE_PLLCLK"),
    ("AHBFreq_Value", "72000000"),
]
PINS = ['set pin "PD0-OSC_IN" RCC_OSC_IN', 'set pin "PD1-OSC_OUT" RCC_OSC_OUT']


def apply(pm, p, order):
    for name, value in order:
        pm.run(p, f'set ip parameters RCC IPParameters {name}')
        pm.run(p, f'set ip parameters RCC "{name}" "{value}"')
    pm.run(p, "clock resolution")
    pm.save(p)
    return p.ioc().get_ip_param("RCC", "PLLCLKFreq_Value")


def main() -> int:
    pm = ProjectManager(max_open=1)
    ws = pathlib.Path("build/clk21").resolve()
    shutil.rmtree(ws, ignore_errors=True)
    ws.mkdir(parents=True)
    pm.workspace = ws

    for tag, order in (("declared", PARAMS), ("reversed", list(reversed(PARAMS)))):
        p = pm.create("T_" + tag)
        pm.load_mcu(p, "STM32F103C8T6")
        pm.run(p, "project toolchain Makefile")
        pm.run(p, "project name T")
        pm.save(p)
        pm.load_ioc(p, p.ioc_path)          # same state CubeMX restores on start
        for c in PINS:
            pm.run(p, c)
        print(tag, "pass1 PLLCLK =", apply(pm, p, order))
        pm.load_ioc(p, p.ioc_path)
        print(tag, "pass2 PLLCLK =", apply(pm, p, order))
        pm.close_all()
    return 0


if __name__ == "__main__":
    sys.exit(main())
