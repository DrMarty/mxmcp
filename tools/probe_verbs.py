"""Probe which NVIC/DMA/GIC verbs are actually live for a project.

The `<instance> <verb>` commands are registered dynamically (see
NVICService.initCommands), so the only reliable inventory is the running
engine. Prints OK/KO per candidate so the tool enums can be made exact.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from mxmcp.engine import Session  # noqa: E402

MCU = "STM32F103C8Tx"
IRQ = "USART1_IRQn"
CANDIDATES = {
    "NVIC": ["get_interrupts", f"get_ip_interrupts USART1", "get_prioritygroup",
             f"get_priority {IRQ}", f"get_subpriority {IRQ}",
             f"get_irqhandlergenerated {IRQ}", f"get_enable_state {IRQ}",
             f"get_group {IRQ}", f"get_preemptsource {IRQ}",
             f"get_startupdelay {IRQ}", "list", "list_all",
             f"enable {IRQ}", f"disable {IRQ}", f"set_priority {IRQ} 1",
             f"set_prioritygroup 4"],
    "dma": ["list_all", "used_flows", f"list USART1_TX",
            f"listbriefly USART1_TX", "list_controller DMA1",
            f"available_streams USART1_TX", f"is_available USART1_TX",
            "get_param", f"get_param USART1_TX Priority",
            f"get_param USART1_TX Priority DMA1_Channel1",
            f"set_param USART1_TX Priority Medium",
            f"set_param USART1_TX Priority Medium DMA1_Channel1",
            f"set_flow USART1_TX Peripheral-To-Memory",
            f"delete USART1_TX"],
}


def main() -> int:
    wd = pathlib.Path("build/verbs")
    wd.mkdir(parents=True, exist_ok=True)
    s = Session(workdir=wd)
    print("load:", s.send(f"load {MCU}", timeout=240).status, flush=True)
    s.send("set pin PA9 USART1_TX", timeout=60)
    s.send('set mode USART1 "Asynchronous"', timeout=60)
    s.send("clock resolution", timeout=60)
    for head, verbs in CANDIDATES.items():
        for v in verbs:
            cmd = f"{head} {v}"
            try:
                r = s.send(cmd, timeout=25)
            except Exception as exc:  # noqa: BLE001
                print(f"{cmd:52s} ERROR {exc}", flush=True)
                break
            body = (r.payload or r.log).strip().replace("\n", " | ")[:80]
            flag = "HUNG" if r.hung else r.status
            print(f"{cmd:52s} {flag:5s} {body}", flush=True)
            if r.hung:
                s = Session(workdir=wd)
                s.send(f"load {MCU}", timeout=240)
    s.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
