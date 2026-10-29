"""Probe GPIO parameter writes through the CLI on a project loaded from .ioc.

Earlier attempts (`set gpio parameters PC13 GPIO_Label LED`) returned KO. The
CLI grammar is `<pin> <param> <value>`, but the match may need the full pin name
(PC13-TAMPER-RTC) or the signal form (GPIO_Output). Also check `get gpio
parameters` with the same forms.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from mxmcp.engine import Session  # noqa: E402


def main() -> int:
    wd = pathlib.Path("probe/gpio2").resolve()
    wd.mkdir(parents=True, exist_ok=True)
    s = Session(workdir=wd)
    cmds = [
        "load STM32F103C8Tx",
        "set pin PC13 GPIO_Output",
        "set mode USART1 Asynchronous",
        "get gpio parameters PC13 GPIO_Label",
        "get gpio parameters PC13-TAMPER-RTC GPIO_Label",
        "get gpio parameters .* GPIO_Label",
        "set gpio parameters PC13 GPIO_Output GPIO_Label LED",
        "set gpio parameters PC13-TAMPER-RTC GPIO_Label LED",
        "set gpio parameters PC13 GPIO_Label LED",
        'set gpio parameters "PC13-TAMPER-RTC" "GPIO_Label" "LED"',
        "get pinout",
    ]
    for c in cmds:
        r = s.send(c, timeout=120)
        print(f"[{r.status}] {r.seconds:5.1f}s {c:56s} -> {r.payload[:80]!r}")
    s.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
