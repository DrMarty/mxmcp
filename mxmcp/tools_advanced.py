"""Tools for the CLI surfaces found by the deep reverse engineering pass.

Covers the services that the first iteration missed because their commands are
registered per plugin jar or built dynamically (`<IP> <verb>` names come from
CommandLineManager.addCommand calls in Mcu/NVICService/DMAService/...):

  dma / mdma / gic / NVIC / MMT (memory map) / MultiConfig (LPBAM) /
  import (project porting & compatibility rules) / selector, boardselector,
  exampleselector / ioc compare (cpload, cpexport) / clock get /
  possible_value + not_a_possible_value / xts, xcopy, xbuild, user_analytics,
  tooltip, simulate, updateIpUI, setprop/getprop/getenv / command registry.
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from . import schema as S
from .rpc import ToolError
from .store import ProjectManager

DATA = Path(__file__).resolve().parent / "data"

# captured from the live engine: `NVIC` with no arguments prints its own table
NVIC_READ = ["get_interrupts", "get_ip_interrupts", "get_prioritygroup",
             "get_priority", "get_subpriority", "get_enable_state",
             "get_irqhandlergenerated", "get_usesfreertosfunctions"]
NVIC_WRITE = ["enable", "disable", "set_prioritygroup", "set_priority",
              "set_subpriority", "set_enable_state", "set_irqhandlergenerated",
              "set_usesfreertosfunctions"]

# `nvic`/`dma` answers arrive either as payload or as log4j lines: merge both.
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _out(res: dict, command: str | None = None) -> str:
    """Merge the stdout payload with the log4j lines a service answered with.

    CubeMX echoes the command on the reply line, and services such as
    `dma list <request>` print their detail block through the logger instead of
    stdout, so both channels belong to one answer.
    """
    payload = [l for l in (res.get("output") or "").splitlines()]
    if command:
        echo = command.strip().lower()
        while payload and payload[0].strip().lower() == echo:
            payload.pop(0)
    text = "\n".join(payload).strip()
    seen = {l.strip().lower() for l in payload if l.strip()}
    extra = [l for l in (res.get("log") or "").splitlines()
             if l.strip() and l.strip().lower() not in seen]
    if not text:
        text = "\n".join(extra).strip()
    elif extra:
        text = text + "\n" + "\n".join(extra)
    return _ANSI.sub("", text).strip()


def _kv(res: dict, command: str | None = None) -> dict:
    """Parse `name:value` / `name value` result lines into a dict."""
    data: dict[str, str] = {}
    for line in _out(res, command).splitlines():
        line = line.strip()
        if not line or line.lower().startswith(line.split(" ")[0].lower() + " "):
            pass
        if ":" in line:
            k, _, v = line.partition(":")
            data[k.strip()] = v.strip()
        elif len(line.split()) == 2:
            k, v = line.split()
            data[k] = v
    return data


def _words(res: dict, command: str | None = None) -> list[str]:
    """Split a whitespace list reply (get_interrupts style)."""
    text = _out(res, command)
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if lines and lines[0].lower().startswith(("nvic", "gic", "dma", "mdma", "mmt")):
        lines = lines[1:] or lines[:1]
    out: list[str] = []
    for line in lines:
        out.extend(line.split())
    return out


def _must_ok(res: dict, label: str) -> str:
    if res["status"] != "OK":
        raise ToolError(f"{label} failed: "
                        f"{(res.get('output') or '')[:400]}")
    return _out(res)


def register(server, pm: ProjectManager) -> None:
    # --------------------------------------------------------------- DMA ----
    def dma_query(args: dict):
        p = pm.get(args["project_id"])
        action = args["action"]
        target = args.get("target")
        table = {
            "list_all": ("dma list_all", None),
            "list": ("dma list", "target required"),
            "list_briefly": ("dma listbriefly", "target required"),
            "list_periph": ("dma list_periph", "target required"),
            "list_controller": ("dma list_controller", "target required"),
            "available_streams": ("dma available_streams", "target required"),
            "available_periph_requests": ("dma available_periph_requests",
                                          "target required"),
            "available_controller_requests": ("dma available_controller_requests",
                                              "target required"),
            "used_flows": ("dma used_flows", None),
            "delete_all": ("dma delete_all", None),
        }
        if action not in table:
            raise ToolError(f"unknown dma action {action!r}; "
                            f"choose from {sorted(table)}")
        base, need = table[action]
        if need and not target:
            raise ToolError(need)
        cmd = f"{base} {target}" if target else base
        res = pm.run(p, cmd, timeout=args.get("timeout", 60))
        return {"project_id": p.pid, "command": cmd, "status": res["status"],
                "text": _out(res, cmd), "items": _words(res, cmd)}

    server.tool(
        "dma_query",
        "Inspect the DMA request/stream map of the project (CubeMX `dma ...` "
        "service): list_all, list, list_briefly, list_periph, list_controller, "
        "available_streams, available_periph_requests, "
        "available_controller_requests, used_flows, delete_all.",
        S.obj({"project_id": S.s("Project id"),
               "action": S.enum(list(["list_all", "list", "list_briefly",
                                      "list_periph", "list_controller",
                                      "available_streams",
                                      "available_periph_requests",
                                      "available_controller_requests",
                                      "used_flows", "delete_all"]), "DMA query"),
               "target": S.s("Request / peripheral / controller name when needed")},
              ["project_id", "action"]), dma_query)

    def dma_mutate(args: dict):
        p = pm.get(args["project_id"])
        kind = args["kind"]
        if kind == "add":
            cmd = f"dma add {args['request']}"
        elif kind == "delete":
            cmd = f"dma delete {args['request']}"
        elif kind == "set_flow":
            cmd = f"dma set_flow {args['request']} {args['flow']}"
        elif kind == "set_param":
            cmd = (f"dma set_param {args['request']} {args['param']} "
                   f"{args['value']}" + (f" {args['flow']}" if args.get("flow") else ""))
        else:  # pragma: no cover - guarded by enum
            raise ToolError(f"unknown kind {kind}")
        res = pm.run(p, cmd, timeout=args.get("timeout", 60))
        _must_ok(res, cmd)
        if args.get("save", True):
            pm.save(p)
        return {"project_id": p.pid, "command": cmd, "status": res["status"],
                "text": _out(res, cmd)}

    server.tool(
        "dma_mutate",
        "Change DMA assignment: add/delete a request, set its flow, or set one "
        "DMA parameter (Priority/Mode/... exactly as CubeMX names them).",
        S.obj({"project_id": S.s("Project id"),
               "kind": S.enum(["add", "delete", "set_flow", "set_param"], "Operation"),
               "request": S.s("DMA request name (e.g. USART2_TX)"),
               "flow": S.s("Flow name for set_flow / optional for set_param"),
               "param": S.s("Parameter name for set_param"),
               "value": S.s("Parameter value for set_param"),
               "save": S.b("Save the project afterwards", True)},
              ["project_id", "kind", "request"]), dma_mutate)

    # -------------------------------------------------------------- MDMA ----
    def mdma_query(args: dict):
        p = pm.get(args["project_id"])
        action = args["action"]
        target = args.get("target")
        table = {
            # names/arity taken verbatim from MDMAService.initCommands
            "list_all_requests": ("mdma list_all_requests", None, 0),
            "list_peripheral_requests": ("mdma list_peripheral_requests",
                                         "target=<peripheral>", 1),
            "list_request": ("mdma list_request", "target=<request>", 1),
            "list_channel_requests": ("mdma list_channel_requests",
                                      "target=<channel>", 1),
            "list_nth_request_on_channel": ("mdma list_nth_request_on_channel",
                                            "target=<channel> index=<n>", 2),
            "delete_all_requests": ("mdma delete_all_requests", None, 0),
        }
        if action not in table:
            raise ToolError(f"unknown mdma action {action!r}; choose from "
                            f"{sorted(table)}")
        base, need, extra = table[action]
        if need and not target:
            raise ToolError(need)
        cmd = base + (f" {target}" if target else "")
        if extra == 2 and action == "list_nth_request_on_channel":
            if args.get("index") is None:
                raise ToolError("list_nth_request_on_channel needs index=<n>")
            cmd = f"{base} {target} {args['index']}"
        res = pm.run(p, cmd, timeout=args.get("timeout", 60))
        return {"project_id": p.pid, "command": cmd, "status": res["status"],
                "text": _out(res, cmd), "items": _words(res, cmd)}

    server.tool(
        "mdma_query",
        "Inspect MDMA (dual-port DMA, H7/U5/N6...) requests and channels via the "
        "CubeMX `mdma ...` service.",
        S.obj({"project_id": S.s("Project id"),
               "action": S.enum(list(["list_all_requests", "list_peripheral_requests",
                                      "list_request", "list_channel_requests",
                                      "list_nth_request_on_channel",
                                      "delete_all_requests"]), "MDMA query"),
               "target": S.s("Channel / request / peripheral name when needed"),
               "index": S.i("Request position for list_nth_request_on_channel")},
              ["project_id", "action"]), mdma_query)

    def mdma_mutate(args: dict):
        p = pm.get(args["project_id"])
        kind = args["kind"]
        if kind == "add_request":
            cmd = f"mdma add_request {args['request']}"
        elif kind == "add_channel_request":
            cmd = f"mdma add_channel_request {args['channel']} {args['request']}"
        elif kind == "delete_request":
            cmd = f"mdma delete_request {args['request']}"
        elif kind == "delete_channel":
            cmd = f"mdma delete_channel {args['channel']}"
        else:  # pragma: no cover
            raise ToolError(f"unknown kind {kind}")
        res = pm.run(p, cmd, timeout=args.get("timeout", 60))
        _must_ok(res, cmd)
        if args.get("save", True):
            pm.save(p)
        return {"project_id": p.pid, "command": cmd, "status": res["status"],
                "text": _out(res, cmd)}

    server.tool(
        "mdma_mutate",
        "Change MDMA assignments/parameters (add_request, add_channel_request, "
        "delete_request, delete_channel, set_param).",
        S.obj({"project_id": S.s("Project id"),
               "kind": S.enum(["add_request", "add_channel_request", "delete_request",
                               "delete_channel"], "Operation"),
               "request": S.s("MDMA request name"),
               "channel": S.s("MDMA channel name (e.g. MDMA_Channel0)"),
               "param": S.s("Parameter name for set_param"),
               "value": S.s("Parameter value for set_param"),
               "save": S.b("Save afterwards", True)},
              ["project_id", "kind"]), mdma_mutate)

    # --------------------------------------------------------------- GIC ----
    def gic_query(args: dict):
        p = pm.get(args["project_id"])
        action = args["action"]
        target = args.get("target")
        table = {"get_interrupts": ("gic get_interrupts", None),
                 "get_ip_interrupts": ("gic get_ip_interrupts", "target required"),
                 "get_enable_state": ("gic get_enable_state", "target required"),
                 "get_triggering_mode": ("gic get_triggering_mode", "target required")}
        if action not in table:
            raise ToolError(f"unknown gic action {action!r}")
        base, need = table[action]
        if need and not target:
            raise ToolError(need)
        cmd = f"{base} {target}" if target else base
        res = pm.run(p, cmd, timeout=args.get("timeout", 60))
        return {"project_id": p.pid, "command": cmd, "status": res["status"],
                "text": _out(res, cmd),
                "items": _words(res, cmd) if action == "get_interrupts" else None,
                "values": _kv(res, cmd) if action == "get_enable_state" else None}

    server.tool(
        "gic_query",
        "Read the GIC interrupt controller (STM32MP1/MP2) through CubeMX: interrupt "
        "list, per-IP interrupts, enable state and triggering mode.",
        S.obj({"project_id": S.s("Project id"),
               "action": S.enum(["get_interrupts", "get_ip_interrupts",
                                 "get_enable_state", "get_triggering_mode"],
                                "GIC query"),
               "target": S.s("IRQ name / index or IP name")},
              ["project_id", "action"]), gic_query)

    def gic_mutate(args: dict):
        p = pm.get(args["project_id"])
        kind = args["kind"]
        parts = {"enable": "gic enable", "disable": "gic disable",
                 "set_triggering_mode": "gic set_triggering_mode"}
        if kind not in parts:
            raise ToolError(f"unknown gic kind {kind!r}")
        cmd = f"{parts[kind]} {args['target']}"
        if args.get("value") is not None:
            cmd += f" {args['value']}"
        res = pm.run(p, cmd, timeout=args.get("timeout", 60))
        _must_ok(res, cmd)
        if args.get("save", True):
            pm.save(p)
        return {"project_id": p.pid, "command": cmd, "status": res["status"],
                "text": _out(res, cmd)}

    server.tool(
        "gic_mutate",
        "Change GIC interrupt routing (enable/disable, enable state, triggering "
        "mode, priority, security).",
        S.obj({"project_id": S.s("Project id"),
               "kind": S.enum(["enable", "disable", "set_triggering_mode"],
                              "Operation"),
               "target": S.s("IRQ name or index"),
               "value": S.s("Value to set when the command takes one"),
               "save": S.b("Save afterwards", True)},
              ["project_id", "kind", "target"]), gic_mutate)

    # -------------------------------------------------------------- NVIC ----
    def nvic_read(args: dict):
        p = pm.get(args["project_id"])
        action = args["action"]
        irq = args.get("irq")
        if action == "get_interrupts":
            cmd = "NVIC get_interrupts"
        elif action == "get_ip_interrupts":
            if not irq:
                raise ToolError("get_ip_interrupts needs irq=<IP name>")
            cmd = f"NVIC get_ip_interrupts {irq}"
        elif action == "get_prioritygroup":
            cmd = "NVIC get_prioritygroup"
        elif action in ("get_usesfreertosfunctions",):
            cmd = f"NVIC {action}"
        else:
            if not irq:
                raise ToolError(f"{action} needs irq=<IRQ name>")
            cmd = f"NVIC {action} {irq}"
        res = pm.run(p, cmd, timeout=args.get("timeout", 60))
        text = _out(res, cmd)
        if action == "get_prioritygroup":
            return {"project_id": p.pid, "command": cmd, "status": res["status"],
                    "priority_group": text.split()[-1] if text.split() else "",
                    "text": text}
        if action in ("get_interrupts", "get_ip_interrupts"):
            items = _words(res, cmd)
            return {"project_id": p.pid, "command": cmd, "status": res["status"],
                    "interrupts": items, "count": len(items), "text": text}
        return {"project_id": p.pid, "command": cmd, "status": res["status"],
                "values": _kv(res, cmd), "text": text}

    server.tool(
        "nvic_read",
        "Read NVIC state: enabled interrupts, an IP's interrupts, the priority "
        "group, and per-IRQ priority / subpriority / handler-generated / enable "
        "state / group / preempt source.",
        S.obj({"project_id": S.s("Project id"),
               "action": S.enum(NVIC_READ, "NVIC query"),
               "irq": S.s("IRQ name (USART1_IRQn) or IP name for get_ip_interrupts")},
              ["project_id", "action"]), nvic_read)

    def nvic_write(args: dict):
        p = pm.get(args["project_id"])
        action = args["action"]
        irq = args.get("irq")
        if action == "set_prioritygroup":
            if args.get("value") is None:
                raise ToolError("set_prioritygroup needs value=0..4")
            cmd = f"NVIC set_prioritygroup {args['value']}"
        else:
            if not irq:
                raise ToolError(f"{action} needs irq=<IRQ name>")
            cmd = f"NVIC {action} {irq}"
            if action.startswith("set_"):
                if args.get("value") is None:
                    raise ToolError(f"{action} needs value=")
                cmd += f" {args['value']}"
        res = pm.run(p, cmd, timeout=args.get("timeout", 60))
        _must_ok(res, cmd)
        if args.get("save", True):
            pm.save(p)
        return {"project_id": p.pid, "command": cmd, "status": res["status"],
                "text": _out(res, cmd)}

    server.tool(
        "nvic_write",
        "Change NVIC: enable/disable an interrupt, set priority/subpriority/group/"
        "preempt source/handler-generated flag, or the priority group.",
        S.obj({"project_id": S.s("Project id"),
               "action": S.enum(NVIC_WRITE, "Operation"),
               "irq": S.s("IRQ name"),
               "value": S.s("Value for the set_* operations"),
               "save": S.b("Save afterwards", True)},
              ["project_id", "action"]), nvic_write)

    # ------------------------------------------- memory map tool (MMT) ----
    def mmt(args: dict):
        p = pm.get(args["project_id"])
        action = args["action"]
        target = args.get("target")
        if action == "dump":
            what = target or "free"
            if what not in ("free", "AppReg", "HRange", "HRegion"):
                raise ToolError("dump target must be free|AppReg|HRange|HRegion")
            cmd = f"MMT dump {what}" + (f" {args['scope']}"
                                        if args.get("scope") else "")
        elif action == "reserved":
            if not args.get("regions"):
                raise ToolError("reserved needs regions=\"FLASH,y,name,0x0,0x100;...\"")
            kind = args.get("kind", "SW")
            if kind not in ("SW", "HW"):
                raise ToolError("kind must be SW or HW")
            cmd = f'MMT reserved {kind} "{args["regions"]}"'
        elif action == "reset_reserved":
            cmd = "MMT resetReserved"
        elif action == "load_pre_config":
            cmd = f'MMT load pre-config "{target}"'
        elif action == "save_pre_config":
            cmd = f'MMT save pre-config "{target}"'
        elif action == "threadx":
            cmd = f"MMT ThreadX {args['value']}"
        else:  # pragma: no cover
            raise ToolError(f"unknown MMT action {action!r}")
        res = pm.run(p, cmd, timeout=args.get("timeout", 90))
        return {"project_id": p.pid, "command": cmd, "status": res["status"],
                "text": _out(res, cmd),
                "note": ("" if res["status"] == "OK" else
                         "MMT commands answer KO when the selected MCU has no "
                         "memory-map feature or the memorymap plugin is not "
                         "applicable to this project")}

    server.tool(
        "mmt",
        "Drive the Memory Mapping Tool (H7RS/U5/N6 TrustZone-style memory map): "
        "dump free/AppReg/HRange/HRegion, reserve SW/HW regions, reset reserved, "
        "load/save pre-config files, enable ThreadX layout.",
        S.obj({"project_id": S.s("Project id"),
               "action": S.enum(["dump", "reserved", "reset_reserved",
                                 "load_pre_config", "save_pre_config", "threadx"],
                                "MMT action"),
               "target": S.s("dump kind (free|AppReg|HRange|HRegion) or file name"),
               "scope": S.s("Optional dump scope: context:<name> or core:<name>"),
               "kind": S.enum(["SW", "HW"], "Reservation owner"),
               "regions": S.s("Semicolon separated region list for reserved"),
               "value": S.enum(["y", "n"], "ThreadX switch")},
              ["project_id", "action"]), mmt)

    # ------------------------------------------------ LPBAM / contexts ----
    def lpbam(args: dict):
        p = pm.get(args["project_id"])
        action = args["action"]
        if action == "list":
            cmd = "MultiConfig getLPBAMConfigurations"
        elif action == "add":
            cmd = f"MultiConfig addLPBAMConfiguration {args['name']}"
        elif action == "delete":
            cmd = f"MultiConfig deleteLPBAMConfiguration {args['name'] or args['index']}"
        elif action == "rename":
            cmd = f"MultiConfig renameLPBAMConfiguration {args['name']} {args['new_name']}"
        elif action == "select":
            cmd = (f"MultiConfig selectLPBAMConfiguration "
                   f"{args['name'] if args.get('name') else args['index']}")
        elif action == "select_project":
            cmd = f"MultiConfig selectMXProject {args['name']}"
        else:  # pragma: no cover
            raise ToolError(f"unknown MultiConfig action {action!r}")
        res = pm.run(p, cmd, timeout=args.get("timeout", 90))
        if args.get("save", True) and res["status"] == "OK":
            pm.save(p)
        return {"project_id": p.pid, "command": cmd, "status": res["status"],
                "text": _out(res, cmd)}

    server.tool(
        "lpbam",
        "Manage LPBAM / multi-context projects (the GUI's Low Power Banana "
        "workflow): list, add, delete, rename, select a configuration or the "
        "active MX project.",
        S.obj({"project_id": S.s("Project id"),
               "action": S.enum(["list", "add", "delete", "rename", "select",
                                 "select_project"], "MultiConfig action"),
               "name": S.s("Configuration / project name"),
               "new_name": S.s("New name for rename"),
               "index": S.i("Numeric context index when a name is not used"),
               "save": S.b("Save afterwards", True)},
              ["project_id", "action"]), lpbam)

    # ------------------------------------------------- import / porting ----
    def porting(args: dict):
        p = pm.get(args["project_id"])
        action = args["action"]
        if action == "open_ioc":
            cmd = f'import openioc "{pm.abs_path(args["ioc"], p.pid)}"'
        elif action == "ip_config":
            cmd = f'import config "{pm.abs_path(args["ioc"], p.pid)}"'
        elif action == "try_auto":
            cmd = f'import try auto import "{pm.abs_path(args["ioc"], p.pid)}"'
        elif action == "try":
            cmd = "import try import"
        elif action == "try_and_log":
            cmd = f'import try import_and_log "{args.get("report", "import.log")}"'
        elif action == "report":
            cmd = f'import get report "{args.get("report", "report.txt")}"'
        elif action == "add_rule":
            cmd = (f'import add_compatibility_rule {args["source_periph"]} '
                   f'{args["dest_periph"]} {args["rule_type"]} "{args["rule_value"]}"')
        elif action == "set_option":
            cmd = f'import set Option "{args["option"]}" "{args["value"]}"'
        elif action == "gpio_constraint":
            cmd = f'import GPIOconstraint "{args["pin"]}" "{args["signal"]}"'
        elif action == "channel_constraint":
            cmd = (f'import channelconstraint {args["dma"]} {args["peripheral"]} '
                   f'{args["request"]} {args["channel"]}')
        elif action == "hack_db":
            cmd = f'import hackmxdb "{args["pin"]}" "{args["signal"]}"'
        else:  # pragma: no cover
            raise ToolError(f"unknown import action {action!r}")
        res = pm.run(p, cmd, timeout=args.get("timeout", 300))
        return {"project_id": p.pid, "command": cmd, "status": res["status"],
                "text": _out(res, cmd), "hung": res["hung"]}

    server.tool(
        "porting",
        "Port a configuration onto another MCU / manage the import engine: "
        "try_auto (import another .ioc into the current MCU), try/try_and_log, "
        "report, compatibility rules, import options and logs, and the MCUs-DB "
        "hack mode used to patch database entries.",
        S.obj({"project_id": S.s("Project id"),
               "action": S.enum(["open_ioc", "ip_config", "try_auto", "try",
                                 "try_and_log", "report", "add_rule", "set_option",
                                 "gpio_constraint", "channel_constraint", "hack_db"],
                                "Import action"),
               "ioc": S.s("Source .ioc for open_ioc / ip_config / try_auto"),
               "report": S.s("Report/log file name"),
               "source_periph": S.s("Source peripheral for add_rule"),
               "dest_periph": S.s("Destination peripheral for add_rule"),
               "rule_type": S.s("Rule type (see CubeMX import rules)"),
               "rule_value": S.s("Rule value"),
               "option": S.s("Manual import option name"),
               "value": S.s("Option value / hack_db signal"),
               "pin": S.s("Pin name for gpio_constraint / hack_db"),
               "signal": S.s("Signal name for gpio_constraint / hack_db"),
               "dma": S.s("DMA controller for channel_constraint"),
               "peripheral": S.s("Peripheral for channel_constraint"),
               "request": S.s("Request for channel_constraint"),
               "channel": S.s("Channel for channel_constraint"),
               "timeout": S.n("Seconds to wait for the import", 300)},
              ["project_id", "action"]), porting)


    # --------------------------------------------- headless selectors ----
    def selectors(args: dict):
        p = pm.get(args["project_id"])
        kind = args["kind"]
        action = args["action"]
        target = args.get("target")
        value = args.get("value")
        real = {
            "selector": {"list mcus": "selector list mcus",
                         "list peripheral": "selector list peripheral",
                         "list selected peripheral": "selector list selected peripheral",
                         "set peripheral": "selector set peripheral",
                         "close": "selector close",
                         "toggle close": "selector toggleclose"},
            "boardselector": {"list boards": "boardselector list boards",
                              "list peripheral": "boardselector list peripheral",
                              "list selected peripheral":
                                  "boardselector list selected peripheral",
                              "set peripheral": "boardselector set peripheral",
                              "close": "boardselector close"},
            "exampleselector": {
                "list examples": "exampleselector list examples",
                "list mculibrary": "exampleselector list mculibrary",
                "list boardlibrary": "exampleselector list boardlibrary",
                "list middleware": "exampleselector list middleware",
                "list selected mculibrary": "exampleselector list selected mculibrary",
                "list selected boardlibrary":
                    "exampleselector list selected boardlibrary",
                "list selected middleware": "exampleselector list selected middleware",
                "set mculibrary": "exampleselector set mculibrary",
                "set boardlibrary": "exampleselector set boardlibrary",
                "set middleware": "exampleselector set middleware",
                "close": "exampleselector close"},
        }[kind]
        if action not in real:
            raise ToolError(f"{kind} supports: {', '.join(sorted(real))}")
        cmd = real[action]
        if action.startswith("set "):
            if not (target and value is not None):
                raise ToolError(f"{action} needs target=<name> value=<value>")
            cmd = f"{cmd} {target} {value}"
        if args.get("open_first"):
            # the tables only exist once the selector dialog has been created;
            # `open` is a modal Swing window, so this is only useful when the
            # engine runs with a display (`-s`/GUI mode)
            pm.run(p, f"{kind} open", timeout=15)
        res = pm.run(p, cmd, timeout=args.get("timeout", 120))
        items = _words(res, cmd)
        return {"project_id": p.pid, "command": cmd, "status": res["status"],
                "text": _out(res, cmd), "items": items,
                "note": ("the selector tables belong to the MCU/board/example dialog; "
                         "in headless (-i) mode the dialog is not created, so these "
                         "answer KO with the global usage. Use catalog_* tools for "
                         "offline selection, or run the engine with a display")}
    server.tool(
        "selectors",
        "Use CubeMX's headless selector tables: enumerate/inspect the MCU finder "
        "columns and filters, the board-manager peripheral tables, and the example "
        "(X-CUBE) library selections.",
        S.obj({"project_id": S.s("Project id"),
               "kind": S.enum(["selector", "boardselector", "exampleselector"],
                              "Which selector"),
               "action": S.s("Sub-command, e.g. 'list mcus' / 'set peripheral'"),
               "target": S.s("Peripheral / library name for set actions"),
               "value": S.s("Value for set actions"),
               "open_first": S.b("Create the dialog first (GUI mode only)", False),
               "timeout": S.n("Seconds to wait", 120)},
              ["project_id", "kind", "action"]), selectors)

    # -------------------------------------------------- ioc comparison ----
    def ioc_compare(args: dict):
        p = pm.get(args["project_id"])
        a1 = pm.abs_path(args["ioc_1"], p.pid)
        a2 = pm.abs_path(args["ioc_2"], p.pid)
        cmds = [f"cpload project1 {a1}"]
        if a2:
            cmds.append(f"cpload project2 {a2} {args.get('label_2', 'project2')}")
        if args.get("open_view"):
            cmds.append("cpload project2 open view")
        cmds.append(f"cpexport {args.get('output', 'compare.txt')}")
        res = pm.run(p, cmds[-1], timeout=args.get("timeout", 300))
        text = _out(res, cmds[-1])
        body = ""
        out = Path(args.get("output", "compare.txt"))
        if not out.is_absolute():
            out = p.dir / out
        if out.exists():
            body = out.read_text(encoding="utf-8", errors="replace")
        return {"project_id": p.pid, "commands": cmds, "status": res["status"],
                "text": text, "report_path": str(out), "report": body[:200_000],
                "note": "cpload project1/project2 and cpexport belong to the "
                        "file-manager compare view; the engine keeps both projects "
                        "loaded side by side"}

    server.tool(
        "ioc_compare",
        "Compare two .ioc files with CubeMX's own differ (cpload project1/2 + "
        "cpexport) and return the report text.",
        S.obj({"project_id": S.s("Project id"),
               "ioc_1": S.s("First .ioc (absolute or project-relative)"),
               "ioc_2": S.s("Second .ioc to compare against (optional)"),
               "label_2": S.s("Display name for the second project"),
               "output": S.s("Report file name (default compare.txt)"),
               "open_view": S.b("Also open the compare view", False),
               "timeout": S.n("Seconds to wait", 300)},
              ["project_id", "ioc_1"]), ioc_compare)

    # ------------------------------------------------ value validation ----
    def value_check(args: dict):
        p = pm.get(args["project_id"])
        ip = args["ip"]
        param = args["parameter"]
        value = str(args["value"])
        lim = args.get("timeout", 60)
        ok = pm.run(p, f"possible_value ip parameters {ip} {param} {value}", timeout=lim)
        bad = pm.run(p, f"not_a_possible_value ip parameters {ip} {param} {value}",
                     timeout=lim)
        cur = pm.run(p, f'get ip parameters {ip} {param}', timeout=lim)
        return {"project_id": p.pid, "ip": ip, "parameter": param, "value": value,
                "is_possible": ok["status"] == "OK",
                "is_not_possible": bad["status"] == "OK",
                "current": _out(cur, f"get ip parameters {ip} {param}"),
                "possible": _out(ok, "possible_value ip parameters")[:400], "not_possible": _out(bad, "not_a_possible_value ip parameters")[:400]}

    server.tool(
        "value_check",
        "Ask CubeMX whether a parameter value is legal for an IP right now "
        "(`possible_value ip parameters` / `not_a_possible_value ip parameters`) — "
        "this evaluates the XML condition expressions (IP dependencies, semaphores, "
        "die variants) instead of guessing.",
        S.obj({"project_id": S.s("Project id"), "ip": S.s("IP/instance name"),
               "parameter": S.s("Parameter name"),
               "value": S.s("Candidate value")},
              ["project_id", "ip", "parameter", "value"]), value_check)

    def mode_pattern(args: dict):
        p = pm.get(args["project_id"])
        cmd = (f'get mode_param_pattern {args["ip"]} {args["mode"]} '
               f'{args["parameter"]}')
        res = pm.run(p, cmd, timeout=args.get("timeout", 45))
        return {"project_id": p.pid, "status": res["status"],
                "pattern": _out(res, cmd)}

    server.tool(
        "mode_pattern",
        "Get the value pattern CubeMX expects for a mode parameter "
        "(`get mode_param_pattern <ip> <mode> <parameter>`).",
        S.obj({"project_id": S.s("Project id"), "ip": S.s("IP name"),
               "mode": S.s("Active mode name"), "parameter": S.s("Parameter name")},
              ["project_id", "ip", "mode", "parameter"]), mode_pattern)

    def submode_state(args: dict):
        p = pm.get(args["project_id"])
        path = args["path"]
        if isinstance(path, str):
            path = [p0 for p0 in path.split(",") if p0]
        cmd = f'get sub-mode-state {args["ip"]} "{",".join(path)}"'
        lim = args.get("timeout", 45)
        res = pm.run(p, cmd, timeout=lim)
        cmd2 = f'get sub-modes {args["ip"]} "{",".join(path)}"'
        res2 = pm.run(p, cmd2, timeout=lim)
        return {"project_id": p.pid, "ip": args["ip"], "path": path,
                "state": _out(res, cmd), "children": _out(res2, cmd2),
                "status": [res["status"], res2["status"]]}

    server.tool(
        "submode_state",
        "Inspect a mode-tree branch: sub-mode enable state and available sub-modes "
        "(`get sub-mode-state` / `get sub-modes`), the same data the peripheral "
        "diagram uses.",
        S.obj({"project_id": S.s("Project id"), "ip": S.s("IP name"),
               "path": S.s("Comma separated mode path, e.g. \"mode,submode1\"")},
              ["project_id", "ip", "path"]), submode_state)

    # --------------------------------------------------- misc services ----
    def ide_bridge(args: dict):
        p = pm.get(args["project_id"])
        action = args["action"]
        if action == "simulate_open":
            cmd = f"simulate cubeIDE {1 if args.get('value', True) else 0}"
        elif action == "is_plugin_error":
            cmd = f"isPluginError {args['plugin']}"
        elif action == "update_ip_ui":
            cmd = f"updateIpUI {args['ip']}"
        elif action == "tooltip_log":
            cmd = f"tooltip log {'on' if args.get('value', True) else 'off'}"
        elif action == "analytics":
            cmd = f"user_analytics {1 if args.get('value', False) else 0}"
        elif action == "codegenerator_mode":
            cmd = "get codegeneratormode"
        elif action == "ip_dependencies":
            cmd = "list ipdependencies"
        elif action == "bsp_status":
            cmd = "get bsp status"
        elif action == "mcu_peripherals":
            cmd = "get mcu_peripherals"
        else:  # pragma: no cover
            raise ToolError(f"unknown action {action!r}")
        res = pm.run(p, cmd, timeout=args.get("timeout", 60))
        return {"project_id": p.pid, "command": cmd, "status": res["status"],
                "text": _out(res, cmd)}

    server.tool(
        "ide_bridge",
        "Service hooks around the main window: simulate the CubeIDE open action, "
        "query a plugin's error state, refresh an IP's UI, toggle the tooltip log, "
        "toggle user analytics, and read the code-generator mode / IP dependencies / "
        "BSP status / MCU peripherals.",
        S.obj({"project_id": S.s("Project id"),
               "action": S.enum(["simulate_open", "is_plugin_error", "update_ip_ui",
                                 "tooltip_log", "analytics", "codegenerator_mode",
                                 "ip_dependencies", "bsp_status", "mcu_peripherals"],
                                "Action"),
               "plugin": S.s("Plugin name for is_plugin_error"),
               "ip": S.s("IP name for update_ip_ui"),
               "value": S.b("Boolean payload for the action", True)},
              ["project_id", "action"]), ide_bridge)

    def compliance(args: dict):
        p = pm.get(args["project_id"])
        action = args["action"]
        if action == "xts":
            cmd = "xts"
        elif action == "xtest":
            cmd = "xtest"
        elif action == "check_modes":
            cmd = "check mcu modes"
        elif action == "check_all_modes":
            cmd = "check mcus modes"
        elif action == "check_all_xml":
            cmd = "check mcus xml"
        elif action == "check_mode":
            cmd = f'check mode enabled {args["ip"]} "{args["mode"]}"'
        elif action == "pinout_placement":
            cmd = "pinout check keep user placement"
        else:  # pragma: no cover
            raise ToolError(f"unknown action {action!r}")
        res = pm.run(p, cmd, timeout=args.get("timeout", 900))
        text = _out(res, cmd)
        problems = [l.strip() for l in text.splitlines()
                    if l.strip() and "is not available" in l]
        return {"project_id": p.pid, "command": cmd, "status": res["status"],
                "text": text[:100_000], "problems": problems,
                "problem_count": len(problems), "hung": res["hung"]}

    server.tool(
        "compliance",
        "Run CubeMX's own consistency checks: xts/xtest suites, `check mcu modes` "
        "(mode availability for the current pin map), the all-MCU mode and XML "
        "audits, a single mode check, and the pinout keep-placement check.",
        S.obj({"project_id": S.s("Project id"),
               "action": S.enum(["xts", "xtest", "check_modes", "check_all_modes",
                                 "check_all_xml", "check_mode",
                                 "pinout_placement"], "Check to run"),
               "ip": S.s("IP for check_mode"), "mode": S.s("Mode for check_mode"),
               "timeout": S.n("Seconds to wait", 900)},
              ["project_id", "action"]), compliance)

    def runtime_props(args: dict):
        # these commands are engine-global; any live project supplies the session
        p = pm.get(args.get("project_id"))
        action = args["action"]
        if action in ("getenv", "getprop"):
            if not args.get("name"):
                raise ToolError(f"{action} needs name=")
            cmd = f"{action} {args['name']}"
        elif action == "setprop":
            cmd = f"setprop {args['name']} {args['value']}"
        elif action == "log":
            cmd = f"log {args.get('value', 'INFO')}"
        else:  # pragma: no cover
            raise ToolError(f"unknown action {action!r}")
        res = pm.run(p, cmd, timeout=args.get("timeout", 60))
        return {"command": cmd, "status": res["status"], "text": _out(res, cmd)}

    server.tool(
        "runtime_props",
        "Read or write the JVM system properties / environment of the running "
        "CubeMX engine and change its log level at runtime.",
        S.obj({"action": S.enum(["getenv", "getprop", "setprop", "log"], "Action"),
               "project_id": S.s("Project id (defaults to the last used)"),
               "name": S.s("Property / variable name"),
               "value": S.s("Value for setprop, or level for log")},
              ["action"]), runtime_props)

    # ------------------------------------------------ product database ----
    def product_db(args: dict):
        from .firmware import default_repository  # noqa: F401  (keeps import warm)
        db = Path(args.get("database") or _finder_db_path())
        if not db or not Path(db).exists():
            raise ToolError(
                "the MCU-finder product database is not installed; it is "
                "downloaded to ~/.stmcufinder/plugins/mcu/cube-finder-db.db by "
                "the CubeMX database refresh (swmgr refresh / the GUI)")
        con = sqlite3.connect(f"file:{Path(db).as_posix()}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        try:
            tables = [r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
            if args.get("table"):
                if args["table"] not in tables:
                    raise ToolError(f"no table {args['table']!r}; tables: "
                                    f"{', '.join(tables)}")
                sql = f'SELECT * FROM "{args["table"]}"'
                lim = int(args.get("limit", 100))
                sql += f" LIMIT {min(lim, 5000)}"
                rows = [dict(r) for r in con.execute(sql)]
                return {"database": str(db), "tables": tables,
                        "table": args["table"], "rows": rows, "count": len(rows)}
            if args.get("search"):
                term = args["search"]
                hits = {}
                for t in tables:
                    cols = [c[1] for c in con.execute(f'PRAGMA table_info("{t}")')]
                    text_cols = [c for c in cols]
                    where = " OR ".join(f'CAST("{c}" AS TEXT) LIKE ?'
                                        for c in text_cols)
                    params = [f"%{term}%"] * len(text_cols)
                    try:
                        n = con.execute(
                            f'SELECT COUNT(*) FROM "{t}" WHERE {where}',
                            params).fetchone()[0]
                    except sqlite3.Error:
                        continue
                    if n:
                        hits[t] = n
                return {"database": str(db), "search": term, "matches_by_table": hits}
            counts = {}
            for t in tables:
                counts[t] = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
            schema = {t: [list(r) for r in con.execute(f'PRAGMA table_info("{t}")')]
                      for t in tables[:5]}
            return {"database": str(db), "tables": tables, "row_counts": counts,
                    "sample_schema_columns": list(schema)}
        finally:
            con.close()

    server.tool(
        "product_db",
        "Query the parametric MCU-finder database (the data behind the product "
        "selector: attributes, CPN/RPN commercial names, resources, features) "
        "read-only. CubeMX downloads it to ~/.stmcufinder; use `swmgr` / the GUI "
        "database refresh to obtain it.",
        S.obj({"database": S.s("Absolute .db path (optional)"),
               "table": S.s("Table to dump"),
               "search": S.s("Substring search across all tables"),
               "limit": S.n("Max rows for a table dump", 100)}), product_db)

    def command_catalog(args: dict):
        reg = _registry()
        if args.get("command"):
            name = args["command"].strip()
            rows = [r for r in reg if r["command"] == name or
                    r["command"].startswith(name + " ")]
            if not rows:
                rows = [r for r in reg if name.lower() in r["command"].lower()]
            return {"query": name, "matches": [
                {"command": r["command"], "argc": r["argc"], "help": r["help"],
                 "registered_by": f"{r['jar']}::{r['registrar']}",
                 "handler_argv": sorted((r.get("handler_facts") or {}).get(
                     "argv_index", []))} for r in rows[:80]]}
        if args.get("jar"):
            jar = args["jar"]
            rows = [r for r in reg if r["jar"] == jar]
        else:
            rows = reg
        heads = {}
        for r in rows:
            head = r["command"].split()[0]
            heads.setdefault(head, []).append(r["command"])
        return {"total": len(rows), "jars": sorted({r["jar"] for r in rows}),
                "command_heads": {k: sorted(v) for k, v in sorted(heads.items())}}

    server.tool(
        "command_catalog",
        "The extracted CLI registry: every command string CubeMX registers, which "
        "jar/class registers it, its arity and its help text. Use it to discover "
        "what `cli` can run; `command=<name>` returns the exact usage.",
        S.obj({"command": S.s("Command name or prefix to look up"),
               "jar": S.s("Filter by jar (app, clock.jar, updater.jar...)")}),
        command_catalog)


# ---------------------------------------------------------------- helpers ----
_REGISTRY: list[dict] | None = None


def _registry() -> list[dict]:
    global _REGISTRY
    if _REGISTRY is None:
        path = DATA / "cli_registry.json"
        if not path.exists():
            raise ToolError("the CLI registry data file is missing "
                            f"({path}); rebuild it with tools/dump_cli_registry.py")
        _REGISTRY = json.loads(path.read_text(encoding="utf-8"))
    return _REGISTRY


def _finder_db_path() -> str | None:
    for p in (Path.home() / ".stmcufinder" / "plugins" / "mcufinder" / "mcu" /
              "cube-finder-db.db",):
        if p.exists():
            return str(p)
    return None
