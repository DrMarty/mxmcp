"""Software package management tools (Cube FW packages, CMSIS-Packs, updates).

Facts learned from the reverse engineering that shape these tools:

  * `pack status <file>` dumps the complete component model as JSON (4-6 MB).
    It works headless and is the reliable way to enumerate packs/components.
  * `pack enable` needs TP_ADVANCED_MODE=on and a *downloaded* (not integrated)
    pack; the built-in peripheral packs (ModelPeripheralPack) are "integrated"
    and therefore never selectable. When the pack is not in the model the CLI
    answers KO and logs `Pack not found in database`.
  * `swmgr install/remove` download from st.com and need a login for some
    payloads; the licence mode argument is `ask` or `deny`.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import schema as S
from .rpc import ToolError
from .store import ProjectManager


def register(server, pm: ProjectManager) -> None:
    def pack_status(args: dict):
        p = pm.get(args["project_id"])
        target = Path(args.get("output") or (p.dir / "pack_status.json"))
        r = pm.run(p, f"pack status {target}", timeout=900)
        if not target.exists():
            raise ToolError(f"pack status produced no file: {r['output'][:300]}")
        data = json.loads(target.read_text(encoding="utf-8", errors="replace"))
        packs = []
        for model in data.get("models", []):
            for pack in model.get("packs", []):
                comps = pack.get("components", [])
                packs.append({
                    "pack": pack.get("id"),
                    "context": model.get("context", ""),
                    "component_count": len(comps),
                    "selected": sum(1 for c in comps if c.get("selected")),
                    "components": comps[: args.get("max_components", 0)]
                    if args.get("max_components") else None,
                })
        q = (args.get("query") or "").lower()
        if q:
            packs = [x for x in packs if q in (x["pack"] or "").lower()]
        return {"project_id": p.pid, "file": str(target), "pack_count": len(packs),
                "packs": packs[: args.get("limit", 200)]}

    server.tool(
        "pack_status",
        "Enumerate every software pack/component visible to the project as "
        "structured JSON (`pack status <file>`): pack ids, component ids, selected "
        "flags and dependency status. Filter with `query`.",
        S.obj({"project_id": S.s("Project id"),
               "output": S.s("Optional JSON output path"),
               "query": S.s("Substring filter on pack id"),
               "limit": S.i("Max packs", 200, 1, 2000),
               "max_components": S.i("Include up to N component ids per pack", 0, 0, 500)},
              ["project_id"]), pack_status)

    def pack_enable(args: dict):
        p = pm.get(args["project_id"])
        parts = [args["vendor"], f'"{args["pack"]}"', args["version"],
                 f'"{args["class"]}"', f'"{args["group"]}"']
        if args.get("variant"):
            parts.append(f'"{args["variant"]}"')
        if args.get("resolve"):
            parts.append("-resolve")
        cmd = "pack enable " + " ".join(parts)
        r = pm.run(p, cmd, timeout=900)
        if r["status"] != "OK":
            raise ToolError(
                "pack enable returned KO. Preconditions: the pack must be "
                "downloaded (not integrated) and CubeMX must see it in the model "
                f"(check pack_status). Last output: {r['output'][:300]}")
        val = pm.run(p, "pack validate", timeout=900)
        saved = pm.save(p) if args.get("save", True) else {}
        return {"project_id": p.pid, "command": cmd, "status": r["status"],
                "validate": val["status"], "saved": saved}

    server.tool(
        "pack_enable",
        "Enable a CMSIS-Pack component (`pack enable <vendor> <pack> <version> "
        "<class> <group> [variant] [-resolve]`) and run `pack validate`.",
        S.obj({"project_id": S.s("Project id"), "vendor": S.s("Pack vendor"),
               "pack": S.s("Pack name (X-CUBE-BLE1/BlueNRG-MS for a bundle)"),
               "version": S.s("Pack version"),
               "class": S.s("Component class"),
               "group": S.s("Component group or group/subgroup"),
               "variant": S.s("Optional component variant"),
               "resolve": S.b("Ask CubeMX to resolve dependencies automatically", True),
               "save": S.b("Persist the .ioc", True)},
              ["project_id", "vendor", "pack", "version", "class", "group"]),
        pack_enable)

    def pack_disable(args: dict):
        p = pm.get(args["project_id"])
        parts = [args["vendor"], f'"{args["pack"]}"', args["version"],
                 f'"{args["class"]}"', f'"{args["group"]}"']
        if args.get("variant"):
            parts.append(f'"{args["variant"]}"')
        r = pm.run(p, "pack disable " + " ".join(parts), timeout=900)
        if r["status"] != "OK":
            raise ToolError(r["output"][:300] or "pack disable failed")
        pm.run(p, "pack validate", timeout=900)
        return {"project_id": p.pid, "disabled": True}

    server.tool(
        "pack_disable",
        "Disable a CMSIS-Pack component and validate the selection.",
        S.obj({"project_id": S.s("Project id"), "vendor": S.s("Pack vendor"),
               "pack": S.s("Pack name"), "version": S.s("Pack version"),
               "class": S.s("Component class"), "group": S.s("Component group"),
               "variant": S.s("Optional variant")},
              ["project_id", "vendor", "pack", "version", "class", "group"]),
        pack_disable)

    def pack_validate(args: dict):
        p = pm.get(args["project_id"])
        r = pm.run(p, "pack validate", timeout=900)
        out = {"project_id": p.pid, "status": r["status"],
               "output": r["output"][:1000]}
        if args.get("save", True):
            out.update(pm.save(p))
        return out

    server.tool(
        "pack_validate",
        "Apply every component enabled since the last validate (`pack validate`) "
        "and persist the .ioc.",
        S.obj({"project_id": S.s("Project id"),
               "save": S.b("Persist the .ioc", True)},
              ["project_id"]), pack_validate)

    def swmgr(args: dict):
        p = pm.get(args["project_id"])
        action = args["action"]
        if action in ("refresh", "connection check", "connection status",
                      "hello", "getSelectedDB"):
            cmd = f"swmgr {action}"
        elif action in ("install", "remove"):
            if not args.get("target"):
                raise ToolError("install/remove need `target`")
            cmd = f"swmgr {action} {args['target']}"
            if action == "install":
                cmd += f" {args.get('licence', 'ask')}"
        elif action == "set_repository":
            cmd = f"swmgr set repository {args['value']}"
        elif action == "set_proxy":
            cmd = f"swmgr set proxy {args['key']} {args['value']}"
        elif action == "set_proxy_auth":
            cmd = "swmgr set proxy authentication " + \
                  ("true" if args.get("value") in ("true", "1", True) else "false")
        else:
            raise ToolError(f"unknown swmgr action {action!r}")
        r = pm.run(p, cmd, timeout=args.get("timeout", 3600))
        return {"project_id": p.pid, "command": cmd, "status": r["status"],
                "output": r["output"][:4000]}

    server.tool(
        "swmgr",
        "Software manager: refresh the package catalogue, install/remove a "
        "STM32Cube firmware package or CMSIS-Pack, change the repository path or "
        "proxy, check connectivity.",
        S.obj({"project_id": S.s("Project id"),
               "action": S.s("Action", ["refresh", "install", "remove",
                                        "connection check", "connection status",
                                        "hello", "getSelectedDB",
                                        "set_repository", "set_proxy",
                                        "set_proxy_auth"]),
               "target": S.s("Pack/FW full name, e.g. stm32cube_f1_1.8.0 or "
                             "STMicroelectronics.X-CUBE-NFC4.1.4.1, or a file path"),
               "licence": S.s("Licence acceptance", ["ask", "deny"], "ask"),
               "key": S.s("Proxy field", ["type", "host", "port", "login", "password"]),
               "value": S.s("Value for set_repository / set_proxy / auth"),
               "timeout": S.i("Seconds", 3600, 60, 7200)},
              ["project_id", "action"]), swmgr)

    def xcubedl(args: dict):
        p = pm.get(args["project_id"])
        r = pm.run(p, f"xcubedl {args['pack']}", timeout=args.get("timeout", 3600))
        return {"project_id": p.pid, "status": r["status"],
                "output": r["output"][:2000]}

    server.tool(
        "xcubedl",
        "Download an X-CUBE pack by name (`xcubedl <packname>`).",
        S.obj({"project_id": S.s("Project id"), "pack": S.s("Pack name"),
               "timeout": S.i("Seconds", 3600, 60, 7200)},
              ["project_id", "pack"]), xcubedl)

    def login(args: dict):
        p = pm.get(args["project_id"])
        remember = "y" if args.get("remember", True) else "n"
        r = pm.run(p, f'login "{args["email"]}" "{args["password"]}" {remember}',
                   timeout=900)
        return {"project_id": p.pid, "status": r["status"],
                "output": r["output"][:600]}

    server.tool(
        "login",
        "Log in to my.st.com for firmware/pack downloads (`login <email> "
        "<password> <remember y|n>`).",
        S.obj({"project_id": S.s("Project id"), "email": S.s("Account email"),
               "password": S.s("Account password"),
               "remember": S.b("Remember the session", True)},
              ["project_id", "email", "password"]), login)

    def logout(args: dict):
        p = pm.get(args["project_id"])
        r = pm.run(p, "logout", timeout=300)
        return {"project_id": p.pid, "status": r["status"]}

    server.tool(
        "logout",
        "End the my.st.com session (`logout`).",
        S.obj({"project_id": S.s("Project id")}, ["project_id"]), logout)
