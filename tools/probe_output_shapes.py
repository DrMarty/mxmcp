"""Capture the *output format* of the data-returning CLI services.

Several services (dma/mdma/gic/MMT/NVIC/...) answer through log4j lines rather
than stdout, and the dynamic command names come from the static registry, so
what is still missing is the exact text shape each command prints. This probe
records payload + log for one representative call per command and writes
analysis/cli_output_shapes.json for the docs and the MCP parsers.
"""
from __future__ import annotations

import json
import pathlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from mxmcp.engine import Session  # noqa: E402

CASES: dict[str, tuple[str, list[str]]] = {
    "f103": ("STM32F103C8Tx", [
        "set pin PA2 USART2_TX", "set mode USART2 Asynchronous",
        "dma list_all", "dma list USART2_TX", "dma listbriefly USART2_TX",
        "dma list_periph USART2", "dma list_controller DMA1",
        "dma available_controller_requests DMA1",
        "dma available_streams USART2_TX", "dma used_flows",
        "dma is_available USART2_TX", "dma is_available_in USART2_TX DMA1",
        "dma get_param USART2_TX Priority",
        "NVIC get_interrupts", "NVIC get_ip_interrupts USART2",
        "NVIC get_prioritygroup", "NVIC get_priority SysTick_IRQn",
        "NVIC get_subpriority SysTick_IRQn",
        "NVIC get_irqhandlergenerated SysTick_IRQn",
        "MMT dump free", "MMT dump AppReg", "MMT dump HRange", "MMT dump HRegion",
        "list ipdependencies", "get bsp status", "get codegeneratormode",
        "possible_value ip parameters RCC PLLMUL",
        "not_a_possible_value ip parameters RCC PLLMUL",
        "get mode_param_pattern USART2 .*", "get sub-mode-state USART2",
        "check mcu modes",
    ]),
    "h7": ("STM32H743ZITx", [
        "dma list_all", "dma list SDMMC1", "dma list BDMA1",
        "mdma list_all_requests", "mdma list_peripheral_requests",
        "mdma list_channel_requests MDMA_Channel0",
        "NVIC get_ip_interrupts USART1",
        "MMT dump free", "MMT dump HRegion",
    ]),
    "mp1": ("STM32MP157AACx", [
        "gic get_interrupts", "gic get_ip_interrupts USART1",
        "gic get_triggering_mode 33", "dma list SDMMC1",
    ]),
}


def main() -> int:
    out = pathlib.Path("analysis/cli_output_shapes.json").resolve()
    report: dict[str, list[dict]] = {}
    for tag, (mcu, cmds) in CASES.items():
        wd = pathlib.Path("analysis") / "shapes" / tag
        wd.mkdir(parents=True, exist_ok=True)
        rows = []
        try:
            s = Session(workdir=wd)
        except Exception as exc:  # noqa: BLE001
            report[tag] = [{"error": str(exc)}]
            continue
        try:
            r = s.send(f"load {mcu}", timeout=240)
            rows.append({"cmd": f"load {mcu}", "status": r.status,
                         "sec": round(r.seconds, 1)})
            for c in cmds:
                try:
                    r = s.send(c, timeout=45)
                except Exception as exc:  # noqa: BLE001
                    rows.append({"cmd": c, "error": str(exc)})
                    break
                rows.append({"cmd": c, "status": r.status,
                             "sec": round(r.seconds, 1),
                             "payload": r.payload[:3000], "log": r.log[:3000]})
                if r.hung:
                    rows.append({"note": f"{c} hung; engine restarted"})
                    break
        finally:
            s.close()
        report[tag] = rows
        print(f"{tag}: {len(rows)} rows", flush=True)
    out.write_text(json.dumps(report, indent=1), encoding="utf-8")
    for tag, rows in report.items():
        print(f"===== {tag}")
        for row in rows:
            if "payload" not in row:
                continue
            body = (row["payload"] or row["log"]).strip().splitlines()
            print(f"  [{row['status']}] {row['cmd']}  -> {len(body)} lines: "
                  f"{' | '.join(body[:3])[:150]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
