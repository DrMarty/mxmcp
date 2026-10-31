"""Live probe of the CLI families that were previously undocumented.

For each family we ask the running engine for its usage (a bare command prints its
sub-command table) and, where safe, run one representative invocation per MCU.
Families that could open a modal dialog (`selector`/`boardselector`/
`exampleselector` open, popupwizard, login_with_gui, ocxtest, xcopy...) are only
probed for usage.

Output: analysis/cli_probe_live.txt — the evidence base for docs/CLI_REFERENCE.md.
"""
from __future__ import annotations

import pathlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from mxmcp.engine import Session  # noqa: E402

FAMILIES = [
    "dma", "mdma", "gic", "MMT", "NVIC", "MultiConfig", "import", "check",
    "possible_value", "not_a_possible_value", "tooltip", "pinout", "list",
    "export", "generate", "project", "get", "set", "reset", "lock", "switch",
    "unset", "disable", "simulate", "user_analytics", "isPluginError",
    "updateIpUI", "cpload", "cpexport", "log", "getenv", "setprop", "getprop",
    "selector", "boardselector", "exampleselector", "add", "clock", "load",
    "loadboard", "tinyload", "waitclock", "csv", "clearpinout", "setDriver",
    "SetStructure", "SetCopyLibrary", "config", "swmgr", "pack", "ocxtest",
    "popupwrapper", "xcopy", "help", "script",
]

EXEC: dict[str, tuple[str, list[str]]] = {
    "f103": ("STM32F103C8Tx", [
        "dma list DMA1", "dma list_all", "dma used_flows",
        "MMT dump free", "get bsp status", "list ipdependencies",
        "isPluginError Clock Configuration", "getprop user.home",
        "tooltip log on", "tooltip log off",
        "set pin PA2 USART2_TX", "dma add DMA1_Channel1",
        "dma list DMA1", "dma get_param",
        "NVIC enable USART2_IRQn", "NVIC set_priority USART2_IRQn 1",
        "NVIC list", "check mode enabled USART2 Asynchronous",
        "get possible remaps USART2_TX", "get available-analog-signals PA2",
    ]),
    "h7": ("STM32H743ZITx", [
        "dma list DMA1", "dma list BDMA1", "mdma list_all_requests",
        "dma listbriefly DMA1", "MMT dump AppReg", "MMT dump HRange",
        "gic get_interrupts", "NVIC list",
        "set ip parameters RCC IPParameters PLL1QDivEnabled",
    ]),
    "mp1": ("STM32MP157AACx", ["gic get_interrupts", "dma list DMA1"]),
    "n6": ("STM32N657X0HxQ", ["MMT dump HRegion", "gic get_interrupts",
                              "dma list DMA1", "MDMA list_all_requests"]),
    "u5": ("STM32U575ZITx", ["dma list DMA1", "mdma list_peripheral_requests",
                             "NVIC set_prioritygroup 4", "NVIC list"]),
}

SESS: dict[str, Session] = {}
FH = None


def emit(title: str, text: str) -> None:
    FH.write(f"\n===== {title}\n")
    FH.write((text or "").strip() + "\n")
    FH.flush()


def ensure(tag: str) -> Session | None:
    """Return a live session for `tag`, restarting and reloading when needed."""
    mcu = EXEC[tag][0]
    s = SESS.get(tag)
    if s is not None and s.alive:
        return s
    wd = pathlib.Path("analysis") / "probe_live" / tag
    wd.mkdir(parents=True, exist_ok=True)
    try:
        s = Session(workdir=wd)
    except Exception as exc:  # noqa: BLE001
        emit(f"[{tag}] session start failed", str(exc))
        return None
    SESS[tag] = s
    r = s.send(f"load {mcu}", timeout=300)
    emit(f"[{tag}] load {mcu}", f"{r.status} {r.seconds:.1f}s")
    return s


def send(tag: str, cmd: str, timeout: float = 90.0):
    s = ensure(tag)
    if s is None:
        return None
    try:
        return s.send(cmd, timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        emit(f"[{tag}] {cmd}", f"engine error: {exc}")
        return None


def main() -> int:
    global FH
    out = pathlib.Path("analysis/cli_probe_live.txt").resolve()
    FH = out.open("w", encoding="utf-8")
    try:
        for tag in EXEC:
            for cmd in EXEC[tag][1]:
                r = send(tag, cmd)
                if r is not None:
                    emit(f"[{tag}] {cmd}", f"{r.status} {r.seconds:.1f}s\n{r.payload[:1500]}")
        # usage tables only need one session
        for fam in FAMILIES:
            r = send("f103", fam, timeout=60)
            if r is not None:
                emit(f"[usage] {fam}", r.payload[:3000])
    finally:
        for s in SESS.values():
            try:
                s.close()
            except Exception:  # noqa: BLE001
                pass
        FH.close()
    print("wrote", out, out.stat().st_size, "bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
