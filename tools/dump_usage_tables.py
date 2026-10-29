"""Dump the complete dynamic verb table for the per-instance services."""
from __future__ import annotations

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from mxmcp.engine import Session  # noqa: E402

HEADS = ["NVIC", "dma", "mdma", "gic", "MMT", "MultiConfig", "selector",
         "boardselector", "exampleselector", "import", "clock", "pinout",
         "project", "config", "set", "get", "list", "check", "generate",
         "export", "csv", "reset", "lock", "unset", "disable", "switch",
         "add", "tooltip", "pack", "swmgr", "cpload", "cpexport", "log"]


def main() -> int:
    wd = pathlib.Path("build/usagetables")
    wd.mkdir(parents=True, exist_ok=True)
    s = Session(workdir=wd)
    print("load:", s.send("load STM32F103C8Tx", timeout=240).status, flush=True)
    out = pathlib.Path("analysis/cli_usage_tables.txt")
    with out.open("w", encoding="utf-8") as fh:
        for head in HEADS:
            try:
                r = s.send(head, timeout=40)
            except Exception as exc:  # noqa: BLE001
                fh.write(f"\n===== {head}: ERROR {exc}\n")
                break
            body = "\n".join(x for x in (r.payload, r.log) if x and x.strip())
            fh.write(f"\n===== {head} [{r.status}]\n{body}\n")
            fh.flush()
            print(f"{head:16s} {r.status} {len(body.splitlines()):4d} lines",
                  flush=True)
            if r.hung:
                s = Session(workdir=wd)
                s.send("load STM32F103C8Tx", timeout=240)
    s.close()
    txt = out.read_text(encoding="utf-8", errors="replace")
    for head in ("NVIC", "gic", "mdma"):
        block = txt.split(f"===== {head} [")[1].split("=====")[0] if f"===== {head} [" in txt else ""
        verbs = sorted(set(re.findall(rf"{head}\s+([a-z_][a-z0-9_]*)", block)))
        print(f"\n{head} verbs ({len(verbs)}): {verbs}")
    print("wrote", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
