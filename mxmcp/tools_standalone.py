"""MCP tools for the standalone engine (no CubeMX installation required).

These tools implement the same operations as the engine-backed ones, but entirely
in Python over the bundled data pack:

  standalone_info      what is available offline (packs, counts, capabilities)
  standalone_create    create a project for an MCU (validated against the db)
  standalone_pin       set/reset a pin signal (validated against the MCU pinout)
  standalone_mode      enable a peripheral/middleware mode
  standalone_param     set an IP parameter
  standalone_nvic      configure an interrupt
  standalone_validate  full consistency check
  standalone_save      write the .ioc
  standalone_generate  generate a C project skeleton

When a CubeMX installation *is* present, the engine-backed tools (project_*,
pin_set, mode_set, project_generate) remain the higher-fidelity path; these
tools are what makes the server usable on a machine without CubeMX.
"""
from __future__ import annotations

from pathlib import Path

from . import schema as S
from .bundle import pack_path
from .ipmodes import IPModes
from .rpc import ToolError
from .standalone import DeviceDB, StandaloneError, StandaloneProject
from .store import WORKSPACE

_SESSIONS: dict[str, StandaloneProject] = {}
_DB: DeviceDB | None = None


def db() -> DeviceDB:
    global _DB
    if _DB is None:
        _DB = DeviceDB()
    return _DB


def _session(args: dict) -> StandaloneProject:
    pid = args.get("project_id") or (next(iter(_SESSIONS), None))
    if not pid or pid not in _SESSIONS:
        raise ToolError("no standalone project is open; "
                        "call standalone_create or standalone_open first")
    return _SESSIONS[pid]


def _save_state(p: StandaloneProject) -> Path:
    d = WORKSPACE / "projects" / p.pid
    d.mkdir(parents=True, exist_ok=True)
    return p.save(d / "project.ioc")


def register(server, pm=None) -> None:   # pm kept for signature compatibility
    def standalone_info(args: dict):
        d = db()
        info = {"data_pack": str(pack_path()),
                "pack_present": d.pack.available,
                "engine_available": _engine_available(),
                "mode": "standalone" if not _engine_available() else "hybrid"}
        if d.pack.available:
            meta = d.pack.meta()
            info.update({"counts": meta.get("counts"),
                         "source_root": meta.get("source_root"),
                         "db_version": meta.get("db_version"),
                         "pack_bytes": d.pack.path.stat().st_size})
        try:
            info["ip_modes"] = IPModes(d.pack).summary()
        except Exception as exc:  # noqa: BLE001
            info["ip_modes_error"] = str(exc)
        info["open_projects"] = sorted(_SESSIONS)
        info["capabilities"] = {
            "offline": ["mcu/board search", "pin functions", "IP mode catalogue",
                        "parameter schemas", "project create/edit/validate",
                        ".ioc read/write", "C code generation", "RTOS schema",
                        "middleware list", "CLI registry"],
            "needs_engine": ["CubeMX-exact generation", "clock tree solve",
                             "firmware package install", "pack/swmgr",
                             "ioc import/compare"],
        }
        return info

    server.tool(
        "standalone_info",
        "Report whether the standalone (no-installation) path is active, what the "
        "bundled data pack contains, and which capabilities are available offline.",
        S.obj({}), standalone_info)

    def standalone_create(args: dict):
        try:
            p = StandaloneProject.create(db(), args["mcu"],
                                         pid=args.get("name") or "project",
                                         toolchain=args.get("toolchain", "Makefile"))
        except StandaloneError as exc:
            raise ToolError(str(exc)) from exc
        _SESSIONS[p.pid] = p
        path = _save_state(p)
        dev = p.device
        return {"project_id": p.pid, "mcu": dev.ref_name, "family": dev.family,
                "package": dev.package, "pins": len(dev.pins),
                "ips": [ip.instance for ip in dev.ips][:40],
                "ioc": str(path)}

    server.tool(
        "standalone_create",
        "Create a project for an MCU using only the bundled database (marketing "
        "part numbers are resolved to the db reference name).",
        S.obj({"mcu": S.s("MCU part number (STM32F103C8T6) or db name"),
               "name": S.s("Project id"),
               "toolchain": S.s("Target toolchain", ["Makefile", "STM32CubeIDE",
                                                     "MDK-ARM", "EWARM", "CMake"],
                                "Makefile")},
              ["mcu"]), standalone_create)

    def standalone_open(args: dict):
        path = Path(args["ioc"]).expanduser()
        if not path.is_absolute():
            path = (WORKSPACE / path).resolve()
        if not path.exists():
            raise ToolError(f"{path} does not exist")
        p = StandaloneProject.load(db(), path)
        _SESSIONS[p.pid] = p
        return {"project_id": p.pid,
                "mcu": p.device.ref_name if p.device else None,
                "pins": len(p.pin_signals), "ips": p.ips(),
                "problems": p.problems()}

    server.tool(
        "standalone_open",
        "Load a .ioc into the standalone engine (no CubeMX needed).",
        S.obj({"ioc": S.s("Path to the .ioc")}, ["ioc"]), standalone_open)

    def standalone_pin(args: dict):
        p = _session(args)
        try:
            if args.get("signal"):
                res = p.set_pin(args["pin"], args["signal"])
            else:
                res = p.reset_pin(args["pin"])
        except StandaloneError as exc:
            raise ToolError(str(exc)) from exc
        return {"project_id": p.pid, **res, "ioc": str(_save_state(p))}

    server.tool(
        "standalone_pin",
        "Bind (or reset) a pin signal with real validation against the MCU "
        "pinout: only signals the pin advertises are accepted, GPIO_* variants "
        "are expanded from the db IOModes, and a signal can only be bound once.",
        S.obj({"project_id": S.s("Project id"),
               "pin": S.s("Pin name (PA9, PC13, PD0-OSC_IN…)"),
               "signal": S.s("Signal to bind, e.g. USART1_TX / GPIO_Output; "
                             "omit to reset the pin")},
              ["pin"]), standalone_pin)

    def standalone_signals(args: dict):
        p = _session(args)
        dev = p.require_device()
        pin = p._full_pin_name(args["pin"])
        if pin is None:
            raise ToolError(f"{args['pin']!r} is not a pin of {dev.ref_name}")
        return {"project_id": p.pid, "pin": pin,
                "signals": dev.signals_for(pin),
                "current": p.pin_signals.get(pin, ""),
                "used_by": [k for k, v in p.pin_signals.items()
                            if v == args.get("signal")] if args.get("signal") else []}

    server.tool(
        "standalone_signals",
        "List the signals a pin can carry (offline, from the bundled MCU xml) and "
        "what it is bound to now.",
        S.obj({"project_id": S.s("Project id"), "pin": S.s("Pin name"),
               "signal": S.s("Optional: who else uses this signal")},
              ["pin"]), standalone_signals)

    def standalone_mode(args: dict):
        p = _session(args)
        try:
            res = p.set_mode(args["ip"], args["mode"])
        except StandaloneError as exc:
            raise ToolError(str(exc)) from exc
        return {"project_id": p.pid, **res, "ioc": str(_save_state(p))}

    server.tool(
        "standalone_mode",
        "Enable a peripheral/middleware mode, validated against the IP's mode list "
        "from db/mcu/IP/*_Modes.xml.",
        S.obj({"project_id": S.s("Project id"), "ip": S.s("IP instance"),
               "mode": S.s("Mode name (Asynchronous, CMSIS_V2, SDIO…)")},
              ["ip", "mode"]), standalone_mode)

    def standalone_param(args: dict):
        p = _session(args)
        res = p.set_ip_param(args["ip"], args["param"], str(args["value"]))
        return {"project_id": p.pid, **res, "ioc": str(_save_state(p))}

    server.tool(
        "standalone_param",
        "Set an IP parameter and register it in <IP>.IPParameters (the same "
        "persistence rule CubeMX uses).",
        S.obj({"project_id": S.s("Project id"), "ip": S.s("IP instance"),
               "param": S.s("Parameter name"), "value": S.s("Value")},
              ["ip", "param", "value"]), standalone_param)

    def standalone_nvic(args: dict):
        p = _session(args)
        row = p.set_nvic(args["irq"], priority=args.get("priority"),
                         subpriority=args.get("subpriority"),
                         enabled=args.get("enabled"))
        return {"project_id": p.pid, **row, "ioc": str(_save_state(p))}

    server.tool(
        "standalone_nvic",
        "Configure an interrupt in the standalone project (priority, subpriority, "
        "enabled state) and persist it in the NVIC.<IRQ> line.",
        S.obj({"project_id": S.s("Project id"), "irq": S.s("IRQ name"),
               "priority": S.i("Preemption priority"),
               "subpriority": S.i("Subpriority"),
               "enabled": S.b("Enable the interrupt")},
              ["project_id", "irq"]), standalone_nvic)

    def standalone_view(args: dict):
        p = _session(args)
        dev = p.require_device()
        return {"project_id": p.pid, "mcu": dev.ref_name,
                "family": dev.family, "package": dev.package,
                "core": dev.core, "flash_bytes": dev.flash, "ram_bytes": dev.ram,
                "ips": p.ips(), "pins": p.pin_signals,
                "pin_meta": p.pin_meta, "ip_params": p.ip_params,
                "nvic": p.nvic, "options": p.options,
                "problems": p.problems(),
                "ioc": p.to_ioc().dumps()}

    server.tool(
        "standalone_view",
        "Full standalone project state (MCU, pins, IP parameters, NVIC, options, "
        "validation problems) plus the .ioc text.",
        S.obj({"project_id": S.s("Project id")}), standalone_view)

    def standalone_validate(args: dict):
        p = _session(args)
        probs = p.problems()
        return {"project_id": p.pid, "ok": not probs, "problems": probs}

    server.tool(
        "standalone_validate",
        "Validate the standalone project: pin/signal legality, duplicate signal "
        "bindings, and IPs that do not exist on the MCU.",
        S.obj({"project_id": S.s("Project id")}), standalone_validate)

    def standalone_generate(args: dict):
        from .codegen import Generator
        p = _session(args)
        outdir = Path(args.get("output_dir") or (WORKSPACE / "gen" / p.pid))
        if not outdir.is_absolute():
            outdir = (WORKSPACE / outdir).resolve()
        gen = Generator(p)
        res = gen.generate(outdir, toolchain=args.get("toolchain",
                                                     "Makefile"),
                           project_name=args.get("name") or p.pid)
        return {"project_id": p.pid, **res}

    server.tool(
        "standalone_generate",
        "Generate a C project (main.c/main.h/MSP/IRQ/Makefile) entirely offline "
        "from the bundled HAL config model — no CubeMX installation involved.",
        S.obj({"project_id": S.s("Project id"),
               "output_dir": S.s("Destination directory"),
               "toolchain": S.s("Toolchain", ["Makefile", "STM32CubeIDE"],
                                "Makefile"),
               "name": S.s("Project name override")}), standalone_generate)

    def standalone_mcu(args: dict):
        d = db()
        q = args.get("query", "")
        if args.get("exact"):
            try:
                dev = d.device(args["exact"])
            except StandaloneError as exc:
                raise ToolError(str(exc)) from exc
            return {"ref_name": dev.ref_name, "family": dev.family,
                    "package": dev.package, "core": dev.core,
                    "flash_bytes": dev.flash, "ram_bytes": dev.ram,
                    "pin_count": len(dev.pins), "ips": len(dev.ips),
                    "pins": [{"name": p.name, "type": p.type,
                              "signals": len(p.selectable())}
                             for p in dev.pins.values()][:100]}
        rows = d.search(q, limit=int(args.get("limit", 25)))
        return {"query": q, "count": len(rows),
                "mcus": [{"ref_name": r.get("ref_name"),
                          "family": r.get("family"),
                          "package": r.get("package")} for r in rows]}

    server.tool(
        "standalone_mcu",
        "Search the bundled MCU database, or dump one device's pins and IPs "
        "(works with no CubeMX installation).",
        S.obj({"query": S.s("Search string (family, package, part number)"),
               "exact": S.s("Exact db RefName to inspect"),
               "limit": S.n("Max rows", 25)}), standalone_mcu)


def _engine_available() -> bool:
    try:
        from .store import CUBEMX_ROOT
        return (Path(CUBEMX_ROOT) / "STM32CubeMX.exe").exists()
    except Exception:  # noqa: BLE001
        return False
