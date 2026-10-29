"""MCU / board / catalog discovery tools (offline: never start the engine)."""
from __future__ import annotations

from . import schema as S
from .rpc import ToolError
from .store import ProjectManager


def register(server, pm: ProjectManager) -> None:
    cat = pm.catalog

    def catalog_index(args: dict):
        return cat.index()

    server.tool(
        "catalog_index",
        "Counts for the local CubeMX database: MCUs per family, boards, IP mode "
        "files, config files and FreeMarker templates. Use before searching.",
        S.obj({}, []), catalog_index)

    def mcu_search(args: dict):
        q = args["query"]
        rows = cat.find_mcu(q, limit=args.get("limit", 25))
        return {"query": q, "count": len(rows), "matches": rows}

    server.tool(
        "mcu_search",
        "Search MCUs by part number or RefName (STM32F103C8T6, STM32F103C(8-B)Tx) "
        "or by prefix (STM32G4). Returns flash/RAM/core/package and the exact "
        "RefName to pass to `load`.",
        S.obj({"query": S.s("Part number, RefName or prefix"),
               "limit": S.i("Max rows", 25, 1, 200)},
              ["query"]), mcu_search)

    def mcu_info(args: dict):
        info = cat.get_mcu(args.get("ref_name") or "")
        if info is None:
            names = cat.resolve_mcu(args.get("ref_name") or "")
            if not names:
                raise ToolError(f"MCU {args.get('ref_name')!r} not found in the database")
            info = cat.get_mcu(names[0])
        out = info.as_dict(with_ips=True)
        out["xml"] = info.file
        return out

    server.tool(
        "mcu_info",
        "Full record for one MCU from db/mcu/<RefName>.xml: attributes, memory, "
        "and every IP instance with its CubeMX IP version and config file.",
        S.obj({"ref_name": S.s("Part number or RefName")}, ["ref_name"]), mcu_info)

    def family_list(args: dict):
        fam = cat.families()
        counts = cat.index()["families"]
        return {"families": [{"family": f, "mcu_count": counts.get(f, 0)} for f in fam]}

    server.tool(
        "family_list",
        "List STM32 families present in the database with MCU counts.",
        S.obj({}, []), family_list)

    def family_mcus(args: dict):
        return {"family": args["family"],
                "mcus": cat.mcus_by_family(args["family"], args.get("limit", 200))}

    server.tool(
        "family_mcus",
        "List the MCUs of one family (e.g. STM32H7) with memory/package metadata.",
        S.obj({"family": S.s("Family name, e.g. STM32F4"),
               "limit": S.i("Max rows", 200, 1, 1000)},
              ["family"]), family_mcus)

    def board_search(args: dict):
        rows = cat.find_board(args["query"], limit=args.get("limit", 25))
        return {"query": args["query"], "count": len(rows), "matches": rows}

    server.tool(
        "board_search",
        "Search ST boards (NUCLEO/DISCO/EVAL) by name fragment.",
        S.obj({"query": S.s("Board name fragment"), "limit": S.i("Max rows", 25, 1, 200)},
              ["query"]), board_search)

    def board_list(args: dict):
        rows = cat.boards()
        return {"count": len(rows), "boards": rows}

    server.tool(
        "board_list",
        "List every board known to the board manager (name, mcu, vendor, source pdsc).",
        S.obj({}, []), board_list)

    def ip_library(args: dict):
        fam = args.get("family", "").upper()
        files = cat.ip_mode_files()
        if fam:
            files = [f for f in files if f"-{fam}" in f or fam.replace("STM32", "") in f]
        q = args.get("query", "").lower()
        if q:
            files = [f for f in files if q in f.lower()]
        return {"count": len(files), "files": files[:args.get("limit", 200)]}

    server.tool(
        "ip_library",
        "List the IP mode-definition files under db/mcu/IP (e.g. ADC-STM32F4xx_"
        "Cube_Modes.xml). Filter by family or name fragment.",
        S.obj({"family": S.s("Family filter, e.g. STM32F4"),
               "query": S.s("Substring filter"),
               "limit": S.i("Max rows", 200, 1, 1000)}), ip_library)

    def template_list(args: dict):
        q = args.get("query", "").lower()
        files = cat.templates()
        if q:
            files = [f for f in files if q in f.lower()]
        return {"count": len(files), "templates": files[:args.get("limit", 300)]}

    server.tool(
        "template_list",
        "List the FreeMarker code templates shipped in db/templates (used by the "
        "generator; also the source for user-template override).",
        S.obj({"query": S.s("Substring filter, e.g. usbd_cdc"),
               "limit": S.i("Max rows", 300, 1, 2000)}), template_list)

    def pin_functions_offline(args: dict):
        """Extract pin/alternate-function data straight from the MCU xml."""
        import xml.etree.ElementTree as ET
        info = cat.get_mcu(args["mcu"])
        if info is None:
            names = cat.resolve_mcu(args["mcu"])
            if not names:
                raise ToolError(f"MCU {args['mcu']!r} not found")
            info = cat.get_mcu(names[0])
        path = cat.db / "mcu" / info.file
        ns = "{http://mcd.rou.st.com/modules.php?name=mcu}"
        tree = ET.parse(path)
        pins = []
        want = args.get("pin")
        for pin in tree.getroot().iter(ns + "Pin"):
            name = pin.get("Name", "")
            if want and want.lower() not in name.lower():
                continue
            entry = {"name": name, "position": pin.get("Position"),
                     "type": pin.get("Type"), "signals": []}
            for sig in pin.iter(ns + "Signal"):
                entry["signals"].append(sig.get("Name", ""))
            pins.append(entry)
        return {"mcu": info.ref_name, "pin_count": len(pins), "pins": pins[:500]}

    server.tool(
        "mcu_pin_functions",
        "Alternate-function table for an MCU read straight from the MCU XML (no "
        "engine). Optional `pin` substring filter. Use get functions/ set pin via "
        "the engine for live availability.",
        S.obj({"mcu": S.s("MCU part number or RefName"),
               "pin": S.s("Optional pin name filter (PA9)")},
              ["mcu"]), pin_functions_offline)

    def fw_packages(args: dict):
        import os
        repo = (args.get("repository")
                or os.path.expanduser("~/STM32Cube/Repository"))
        from pathlib import Path
        root = Path(repo)
        packs = []
        if root.is_dir():
            for d in sorted(root.iterdir()):
                if d.is_dir() and (d / "package.xml").exists():
                    try:
                        txt = (d / "package.xml").read_text(
                            encoding="iso-8859-1", errors="replace")
                        import re
                        m = re.search(r'Release="([^"]+)"', txt)
                        rel = m.group(1) if m else ""
                    except Exception:
                        rel = ""
                    packs.append({"name": d.name, "release": rel, "path": str(d)})
        return {"repository": str(root), "count": len(packs), "packages": packs}

    server.tool(
        "firmware_packages",
        "List installed STM32Cube firmware packages in the local repository "
        "(these are what `project generate` copies Drivers from).",
        S.obj({"repository": S.s("Override the repository path")}), fw_packages)
