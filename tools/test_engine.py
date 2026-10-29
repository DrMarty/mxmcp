"""Round-trip test of the warm engine session."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from mxmcp.engine import Session  # noqa: E402


def main() -> int:
    wd = Path("probe/engine").resolve()
    t0 = time.time()
    s = Session(workdir=wd)
    print(f"session up in {time.time()-t0:.1f}s")
    steps = [
        "get version",
        "load STM32F103C8Tx",
        "get mcu name",
        "get mcu package",
        "get mcu peripherals",
        "set pin PC13 GPIO_Output",
        "get signal PC13.*",
        "set pin PA9 USART1_TX",
        "set pin PA10 USART1_RX",
        "set mode USART1 Asynchronous",
        "get mapped modes USART1",
        "check mode enabled USART1 Asynchronous",
        "project path " + str(wd),
        "project name EngT",
        "config saveas EngT.ioc",
        "definitelynotacommand",
    ]
    results = []
    for cmd in steps:
        r = s.send(cmd, timeout=180)
        results.append({"cmd": cmd, "status": r.status, "sec": round(r.seconds, 2),
                        "payload_lines": len(r.payload.splitlines())})
        head = "\n      ".join(r.payload.splitlines()[:3])
        print(f"[{r.status}] {r.seconds:6.2f}s  {cmd}\n      {head}")
    s.close()
    print(json.dumps(results, indent=1))
    print("ioc:", (wd / "EngT" / "EngT.ioc").exists())
    return 0


if __name__ == "__main__":
    sys.exit(main())
