"""Verify RTOS enablement + object persistence through the store API."""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from mxmcp.store import ProjectManager  # noqa: E402

ws = pathlib.Path("build/rtosdbg").resolve()
import shutil

shutil.rmtree(ws, ignore_errors=True)
ws.mkdir(parents=True)
pm = ProjectManager(max_open=1)
pm.workspace = ws
p = pm.create("R1")
pm.load_mcu(p, "STM32F103C8T6")
pm.run(p, "project toolchain Makefile")
r = pm.run(p, 'set mode "FREERTOS" "CMSIS_V2"')
print("quoted :", r["status"], r["output"][:80], "|", (r["log"] or "")[:80])
r = pm.run(p, "set mode FREERTOS CMSIS_V2")
print("bare   :", r["status"], r["output"][:80], "|", (r["log"] or "")[:80])
pm.save(p)
ioc = p.ioc()
ext = p.dir / "project_ext.ioc"
print("ioc ips:", ioc.ips)
print("ext exists:", ext.exists())
if ext.exists():
    merged = ioc.merged(ext)
    print("merged has FREERTOS:", merged.get("FREERTOS.Tasks01")[:60])
    print("Mcu.IP list:", [merged.get(k) for k in merged.keys("Mcu.IP")])
    print("tasks keys:", [k for k in merged.keys("FREERTOS.") if "Tasks" in k][:5])
pm.close_all()
