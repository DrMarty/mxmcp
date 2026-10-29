"""Middleware (add-on IP) support: the integrable component list and custom ones.

CubeMX integrates middleware by name: the instances come from
`MiddleWareConstants` (`FREERTOS`, `THREADX`, `FATFS`, `USB_HOST`, `USB_Device`,
`LWIP`, `MBEDTLS`, `FILEX`, `LEVELX`, `NETX`, `USBX`, `OPENAMP`, `KMS`,
`TOUCHSENSING`, `GUI_INTERFACE`, `STM32_WPAN`, `STM32_BLE`, `LORAWAN`, `SIGFOX`,
`WMBUS`, `USBPD`, `PDM2PCM`, `SUBGHZ_PHY`, `EXTMEM_MANAGER…`, plus `_M4/_M7`
multi-core variants). Enabling one is `set mode <name> "<mode>"`, which then
appears in `Mcu.IPn`; its tables land in `project_ext.ioc`.

Custom middleware (X-CUBE style) is registered with
`add mw <name> <root_dir> <mode_file> <config_file> <template_dir>`.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import schema as S
from .rpc import ToolError
from .store import ProjectManager

DATA = Path(__file__).resolve().parent / "data" / "middleware.json"


def _table() -> dict:
    if not DATA.exists():
        raise ToolError("middleware snapshot missing; run "
                        "tools/middleware_constants.py")
    return json.loads(DATA.read_text(encoding="utf-8"))


def register(server, pm: ProjectManager) -> None:
    def middleware_list(args: dict):
        table = _table()
        names = table["names"]
        if args.get("name"):
            q = args["name"].lower()
            names = [n for n in names if q in n.lower()]
        active = []
        try:
            p = pm.get(args.get("project_id"))
            ioc = p.ioc().merged(p.dir / "project_ext.ioc")
            for k in ioc.keys("Mcu.IP"):
                v = ioc.get(k)
                if v and not v.isdigit():
                    active.append(v)
        except Exception:  # noqa: BLE001 - no project is a valid state here
            p = None
        return {"known_middleware": names,
                "constant_to_name": table["name_by_constant"],
                "template_hooks": table["templates"],
                "active_in_project": sorted(set(active)),
                "how_to_enable": "`set mode <name> <mode>` (see mode_list), then "
                                 "the IP joins Mcu.IPn and its tables are written "
                                 "to project_ext.ioc on save",
                "custom_middleware": "`add mw <name> <root_dir> <mode_file> "
                                     "<config_file> <template_dir>`"}

    server.tool(
        "middleware_list",
        "Every middleware instance CubeMX can integrate (from MiddleWareConstants), "
        "the template hooks each one generates, which are active in the project, "
        "and how to enable or register a custom one.",
        S.obj({"project_id": S.s("Project id (optional, to report the active set)"),
               "name": S.s("Substring filter")}), middleware_list)

    def middleware_add(args: dict):
        p = pm.get(args.get("project_id"))
        name = args["name"]
        if args.get("custom"):
            for key in ("root_dir", "mode_file", "config_file", "template_dir"):
                if not args.get(key):
                    raise ToolError(f"custom middleware needs {key}=")
            cmd = (f'add mw "{name}" "{pm.abs_path(args["root_dir"], p.pid)}" '
                   f'"{pm.abs_path(args["mode_file"], p.pid)}" '
                   f'"{pm.abs_path(args["config_file"], p.pid)}" '
                   f'"{pm.abs_path(args["template_dir"], p.pid)}"')
            res = pm.run(p, cmd, timeout=args.get("timeout", 300))
            return {"project_id": p.pid, "command": cmd, "status": res["status"],
                    "output": (res["output"] or res["log"])[:800]}
        mode = args.get("mode")
        if not mode:
            raise ToolError("enable needs mode=<mode name>; use mode_list "
                            f"after `set ip parameters {name} …`, or pass custom "
                            "files with custom=true")
        attempts = [f'set mode "{name}" "{mode}"', f"set mode {name} {mode}"]
        last = None
        for cmd in attempts:
            last = pm.run(p, cmd)
            if last["status"] == "OK":
                break
        if last["status"] != "OK":
            raise ToolError(f"set mode rejected for {name}/{mode}: "
                            f"{last['output'][:300]}")
        pm.save(p)
        ioc = p.ioc().merged(p.dir / "project_ext.ioc")
        ips = [ioc.get(k) for k in ioc.keys("Mcu.IP") if not ioc.get(k).isdigit()]
        return {"project_id": p.pid, "command": last["command"],
                "status": last["status"], "ips": ips,
                "log": (last.get("log") or "")[:300]}

    server.tool(
        "middleware_add",
        "Integrate a middleware instance (`set mode <name> <mode>`) or register a "
        "custom X-CUBE middleware (`add mw` with root/mode/config/template paths).",
        S.obj({"project_id": S.s("Project id"),
               "name": S.s("Middleware instance name (FREERTOS, FATFS, LWIP…)"),
               "mode": S.s("Mode to activate, e.g. CMSIS_V2 / FATFS / LwIP"),
               "custom": S.b("Register custom middleware files instead", False),
               "root_dir": S.s("Custom middleware root directory"),
               "mode_file": S.s("Custom middleware mode file"),
               "config_file": S.s("Custom middleware config file"),
               "template_dir": S.s("Custom middleware template directory"),
               "timeout": S.n("Seconds to wait", 300)},
              ["project_id", "name"]), middleware_add)
