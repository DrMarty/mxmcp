"""Capture dma/gic log-channel replies + the full NVIC verb table.

`dma …` and `gic …` services answer through log4j lines (filtered out of the
plain payload), and the `NVIC` usage dump lists every dynamically registered
verb. This probe records both so the MCP enums can be exact.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from mxmcp.engine import Session  # noqa: E402

CMDS = ["NVIC", "dma list_all", "dma used_flows", "dma list USART1_TX",
        "dma listbriefly USART1_TX", "dma list_periph USART1",
        "dma available_streams USART1_TX", "dma available_controller_streams USART1_TX DMA1",
        "dma available_periph_requests USART1", "dma available_controller_requests DMA1",
        "dma is_available_in USART1_TX DMA1", "dma get_param USART1_TX PeripheralDataSize",
        "dma set_flow USART1_TX PERIPH_TO_MEMORY", "mdma list_all_requests",
        "gic get_interrupts"]


def main() -> int:
    wd = pathlib.Path("build/dmalog")
    wd.mkdir(parents=True, exist_ok=True)
    s = Session(workdir=wd)
    print("load:", s.send("load STM32F103C8Tx", timeout=240).status, flush=True)
    s.send("set pin PA9 USART1_TX", timeout=60)
    s.send('set mode USART1 "Asynchronous"', timeout=60)
    s.send("dma add USART1_TX", timeout=60)
    for c in CMDS:
        try:
            r = s.send(c, timeout=45, keep_log=True)
        except Exception as exc:  # noqa: BLE001
            print(f"{c:48s} ERROR {exc}", flush=True)
            break
        body = " | ".join(l for l in (r.payload or r.log).splitlines() if l.strip())
        print(f"### {c}  [{r.status}]")
        print("  payload:", (r.payload or "").replace("\n", " | ")[:400])
        print("  log    :", (r.log or "").replace("\n", " | ")[:600], flush=True)
        if r.hung:
            s = Session(workdir=wd)
            s.send("load STM32F103C8Tx", timeout=240)
    s.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
