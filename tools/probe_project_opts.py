"""Probe project-option commands and a real generation from a warm session."""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from mxmcp.engine import Session  # noqa: E402


def main() -> int:
    wd = pathlib.Path("probe/tool").resolve()
    wd.mkdir(parents=True, exist_ok=True)
    s = Session(workdir=wd)
    cmds = [
        "get version",
        "load STM32F103C8Tx",
        "project path " + str(wd),
        "project name ToolT",
        "project toolchain Makefile",
        "project compiler GCC",
        "SetStructure Basic",
        'SetCopyLibrary "copy only"',
        "project set stacksize 0x800",
        "project get stacksize",
        "project set heapsize 0x400",
        "project get heapsize",
        "project couplefilesbyip 1",
        "project generate",
    ]
    for cmd in cmds:
        r = s.send(cmd, timeout=420)
        print(f"[{r.status}] {r.seconds:6.1f}s  {cmd}")
        if r.payload:
            print("   " + r.payload.replace("\n", "\n   ")[:500])
    s.close()
    files = sorted(str(p.relative_to(wd)) for p in wd.rglob("*") if p.is_file())
    print(f"generated {len(files)} files")
    for f in files[:30]:
        print("  ", f)
    return 0


if __name__ == "__main__":
    sys.exit(main())
