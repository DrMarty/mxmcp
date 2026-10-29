"""Project generation step by step, capturing what actually lands on disk."""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from mxmcp.engine import Session  # noqa: E402


def tree(root: pathlib.Path) -> set[str]:
    return {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()}


def main() -> int:
    base = pathlib.Path("probe/gen").resolve()
    log = []
    for name, toolchain, cmds_extra in [
        ("mk", "Makefile", []),
        ("cubeide", "STM32CubeIDE", ["project generateunderroot 1"]),
        ("mdk", "MDK-ARM", ["project couplefilesbyip 0"]),
    ]:
        wd = base / name
        if wd.exists():
            import shutil
            shutil.rmtree(wd, ignore_errors=True)
        wd.mkdir(parents=True, exist_ok=True)
        s = Session(workdir=wd)
        commands = [
            "load STM32F103C8Tx",
            f"project path {wd}",
            f"project name {name.upper()}App",
            f"project toolchain {toolchain}",
            "set pin PC13 GPIO_Output",
            "set pin PA9 USART1_TX",
            "set pin PA10 USART1_RX",
            "set mode USART1 Asynchronous",
            "project generate",
        ] + cmds_extra + ["project generate"]
        steps = []
        for cmd in commands:
            r = s.send(cmd, timeout=600)
            steps.append({"cmd": cmd, "status": r.status, "sec": round(r.seconds, 1),
                          "payload": r.payload[:300]})
        # save project too
        r = s.send(f"config saveas {name}.ioc", timeout=120)
        steps.append({"cmd": "config saveas", "status": r.status, "sec": round(r.seconds, 1),
                      "payload": r.payload[:300]})
        s.close()
        files = tree(wd)
        log.append({"toolchain": toolchain, "workdir": str(wd), "steps": steps,
                    "file_count": len(files),
                    "top_dirs": sorted({f.split("\\")[0] for f in files}),
                    "ioc": sorted(f for f in files if f.endswith(".ioc")),
                    "c_sources": sorted(f for f in files if f.endswith((".c", ".h")))[:40]})
        print(json.dumps(log[-1], indent=1)[:2500])
    (base / "report.json").write_text(json.dumps(log, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
