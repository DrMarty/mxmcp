"""Raw CLI bridge + verification + .ioc direct editing tools.

These exist so the MCP surface stays a *superset* of the CubeMX CLI: any command
the GUI/CLI supports (including ones this server has no dedicated tool for) can
be executed verbatim, and the output is returned as text.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from . import schema as S
from .rpc import ToolError
from .store import ProjectManager
from .tools_pins import _dedupe_suffix

# Commands that are safe to run headless. Anything else is rejected unless
# the caller sets allow_unsafe (e.g. `exit`, `login`, GUI dialogs).
SAFE_HEADS = {
    "get", "set", "reset", "lock", "unlock", "clearpinout", "check", "csv",
    "generate", "list", "possible_value", "not_a_possible_value", "load",
    "loadboard", "tinyload", "waitclock", "switch", "unset", "pinout", "export",
    "import", "config", "project", "setdriver", "setstructure", "setcopylibrary",
    "updateipui", "ispluginerror", "tooltip", "clock", "nvic", "dma", "pack",
    "swmgr", "help", "multiconfig", "add", "disable", "simulate", "user_analytics",
    "xcopy", "xtest", "xts", "xbuild", "xcubedl", "getprop", "setprop", "getenv",
    "popupwrapper", "ocxtest", "cpload", "cpexport",
}


def register(server, pm: ProjectManager) -> None:
    def raw(args: dict):
        p = pm.get(args["project_id"])
        cmd = args["command"].strip()
        head = cmd.split()[0].lower() if cmd else ""
        if head not in SAFE_HEADS and not args.get("allow_unsafe"):
            raise ToolError(f"command {head!r} is not in the safe list; set "
                            "allow_unsafe=true if you really want it")
        r = pm.run(p, cmd, timeout=args.get("timeout", 1800))
        out = {"project_id": p.pid, "command": cmd, "status": r["status"],
               "output": r["output"], "seconds": r["seconds"]}
        if args.get("save"):
            try:
                out["saved"] = pm.save(p)
            except Exception as exc:  # noqa: BLE001
                out["save_error"] = str(exc)[:300]
        return out

    server.tool(
        "cli",
        "Run any CubeMX CLI command verbatim in the project engine and return its "
        "output (OK/KO plus payload). Covers the entire command language: get/set/"
        "reset/lock/check/csv/generate/project/config/pinout/switch/unset/export/"
        "import/NVIC/dma/pack/swmgr/clock/... Optionally save afterwards.",
        S.obj({"project_id": S.s("Project id"),
               "command": S.s("Exact CLI line, e.g. `get mapped modes .*`"),
               "save": S.b("Persist the .ioc after the command", False),
               "allow_unsafe": S.b("Permit commands outside the safe list", False),
               "timeout": S.i("Seconds", 1800, 10, 7200)},
              ["project_id", "command"]), raw)

    def cli_batch(args: dict):
        p = pm.get(args["project_id"])
        cmds = args["commands"]
        results = []
        stopped = None
        for c in cmds:
            head = c.split()[0].lower() if c.strip() else ""
            if head not in SAFE_HEADS and not args.get("allow_unsafe"):
                stopped = c
                break
            r = pm.run(p, c, timeout=args.get("timeout", 1800))
            results.append({"command": c, "status": r["status"],
                            "output": r["output"][:4000]})
            if r["status"] != "OK" and not args.get("continue_on_error"):
                break
        out = {"project_id": p.pid, "results": results,
               "stopped_at": stopped, "count": len(results)}
        if args.get("save"):
            out["saved"] = pm.save(p)
        return out

    server.tool(
        "cli_batch",
        "Run several CLI commands in order (stops at the first KO unless "
        "continue_on_error). Ideal for replaying `project_export_script` output.",
        S.obj({"project_id": S.s("Project id"),
               "commands": S.arr("CLI lines", S.s("command")),
               "continue_on_error": S.b("Keep going after KO", False),
               "allow_unsafe": S.b("Permit commands outside the safe list", False),
               "save": S.b("Persist at the end", True),
               "timeout": S.i("Seconds per command", 1800, 10, 7200)},
              ["project_id", "commands"]), cli_batch)

    def cli_help(args: dict):
        heads = args.get("commands") or [
            "get", "set", "reset", "project", "config", "load", "loadboard",
            "generate", "csv", "export", "import", "pinout", "switch", "unset",
            "clock", "check", "list", "add", "disable", "SetStructure",
            "SetCopyLibrary", "setDriver", "MultiConfig", "swmgr", "pack"]
        p = pm.get(args["project_id"])
        out = {}
        for h in heads:
            r = pm.run(p, h, timeout=120)
            out[h] = r["output"]
        return {"project_id": p.pid, "help": out}

    server.tool(
        "cli_help",
        "Per-family usage tables straight from the engine (running the bare "
        "command prints its sub-command list).",
        S.obj({"project_id": S.s("Project id"),
               "commands": S.arr("Command families to query", S.s("command"))},
              ["project_id"]), cli_help)

    # ----------------------------------------------------------- ioc editing
    def ioc_get(args: dict):
        p = pm.get(args["project_id"])
        if not p.ioc_path.exists():
            pm.save(p)
        ioc = p.ioc()
        key = args.get("key")
        if key:
            return {"project_id": p.pid, "key": key, "value": ioc.get(key)}
        prefix = args.get("prefix")
        rows = {k: v for k, v in ioc.entries.items()
                if not prefix or k.startswith(prefix)}
        return {"project_id": p.pid, "count": len(rows), "entries": rows}

    server.tool(
        "ioc_get",
        "Read raw keys from the saved .ioc: one `key`, or all keys with an "
        "optional `prefix` (e.g. 'RCC.' or 'PA9.').",
        S.obj({"project_id": S.s("Project id"), "key": S.s("Exact key"),
               "prefix": S.s("Key prefix filter")},
              ["project_id"]), ioc_get)

    def ioc_set(args: dict):
        p = pm.get(args["project_id"])
        if not p.ioc_path.exists():
            pm.save(p)
        ioc = p.ioc()
        changes = dict(args.get("entries") or {})
        if args.get("key"):
            changes[args["key"]] = args.get("value", "")
        if not changes:
            raise ToolError("provide key/value or entries")
        for k, v in changes.items():
            ioc.set(k, str(v))
        ioc.save(p.ioc_path)
        if args.get("reload", True):
            pm.load_ioc(p, p.ioc_path)
        return {"project_id": p.pid, "changed": changes,
                "reloaded": bool(args.get("reload", True))}

    server.tool(
        "ioc_set",
        "Write raw keys into the saved .ioc and reload it into the engine. Used "
        "for values the CLI cannot address (GPIO parameters, custom constants).",
        S.obj({"project_id": S.s("Project id"), "key": S.s("Key"),
               "value": S.s("Value"), "entries": S.anyobj("key -> value map"),
               "reload": S.b("Reload into the engine", True)},
              ["project_id"]), ioc_set)

    def ioc_delete(args: dict):
        p = pm.get(args["project_id"])
        ioc = p.ioc()
        key = args["key"]
        ioc.drop(key)
        ioc.save(p.ioc_path)
        if args.get("reload", True):
            pm.load_ioc(p, p.ioc_path)
        return {"project_id": p.pid, "removed": key}

    server.tool(
        "ioc_delete",
        "Delete one key from the saved .ioc and reload it.",
        S.obj({"project_id": S.s("Project id"), "key": S.s("Key to delete"),
               "reload": S.b("Reload into the engine", True)},
              ["project_id", "key"]), ioc_delete)

    def ioc_export(args: dict):
        p = pm.get(args["project_id"])
        src = p.ioc_path
        if not src.exists():
            pm.save(p)
        dst = Path(args["path"]).expanduser()
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        return {"project_id": p.pid, "exported": str(dst)}

    server.tool(
        "ioc_export",
        "Copy the project .ioc to an arbitrary path (shareable artifact).",
        S.obj({"project_id": S.s("Project id"), "path": S.s("Destination .ioc")},
              ["project_id", "path"]), ioc_export)

    def ioc_import(args: dict):
        name = args.get("name") or Path(args["path"]).stem
        pid = pm.new_id(name)
        p = pm.create(pid)
        src = Path(args["path"]).expanduser()
        if not src.exists():
            raise ToolError(f".ioc not found: {src}")
        info = pm.load_ioc(p, src)
        out = pm.save(p)
        return {"project_id": pid, **info, "ioc": out["ioc"]}

    server.tool(
        "ioc_import",
        "Import an external .ioc as a new project (loads it and normalises it "
        "through a save).",
        S.obj({"path": S.s("Path to the .ioc"), "name": S.s("Project name")},
              ["path"]), ioc_import)

    # ----------------------------------------------------------- verification
    def verify(args: dict):
        p = pm.get(args["project_id"])
        if not p.ioc_path.exists():
            raise ToolError("no saved .ioc; run project_save first")
        ioc = p.ioc()
        problems = []
        # 1. MCU consistency
        mcu = pm.run(p, "get mcu name")["output"].strip()
        if mcu and ioc.mcu_name and mcu != ioc.mcu_name:
            problems.append(f"live MCU {mcu!r} != saved {ioc.mcu_name!r}")
        # 2. pin/signal consistency
        pinout = {}
        raw = pm.run(p, "get pinout")["output"]
        for line in raw.splitlines():
            if ":" in line:
                pin, sig = line.split(":", 1)
                pinout[pin.strip()] = _dedupe_suffix(sig)
        for pin in ioc.pins:
            if pin.startswith("VP_"):
                continue
            saved = ioc.pin_state(pin).signal
            live = pinout.get(pin)
            if live is None:
                problems.append(f"pin {pin} saved but not present live")
            elif saved and live != saved:
                problems.append(f"pin {pin}: saved {saved!r} live {live!r}")
        # 3. peripheral legality
        bad = []
        for ip_line in pm.run(p, "get mapped modes .*")["output"].splitlines():
            if "no modes set" in ip_line or ":" not in ip_line:
                continue
            name = ip_line.split(":", 1)[0].strip()
            bad.append(name)
        check = pm.run(p, "check mcu modes")
        unavailable = [l for l in check["output"].splitlines() if "not available" in l]
        # 4. generation dry-run on request
        gen = None
        if args.get("generate"):
            gen = pm.run(p, "project generate", timeout=3600)
            if gen["status"] != "OK":
                problems.append(f"project generate returned {gen['status']}: "
                                f"{gen['output'][:200]}")
        return {"project_id": p.pid, "mcu": ioc.mcu_name,
                "pins_checked": len(ioc.pins), "active_ips": bad,
                "unavailable_modes": len(unavailable),
                "generation": gen["status"] if gen else None,
                "problems": problems,
                "ok": not problems,
                "note": "problems lists live-vs-saved divergence; generation is "
                        "only exercised when generate=true"}

    server.tool(
        "verify",
        "Cross-check live engine state against the saved .ioc: MCU, every pin "
        "signal, active IP modes, plus an optional generation run. Returns a "
        "problem list (empty = consistent).",
        S.obj({"project_id": S.s("Project id"),
               "generate": S.b("Also run project generate as the final check",
                               False)},
              ["project_id"]), verify)
