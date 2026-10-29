"""Project lifecycle tools."""
from __future__ import annotations

from pathlib import Path

from . import schema as S
from .rpc import ToolError
from .store import CUBEMX_ROOT, WORKSPACE, ProjectManager


def register(server, pm: ProjectManager) -> None:
    # ---------------------------------------------------------------- list
    def project_list(args: dict):
        return {"workspace": str(WORKSPACE), "cubemx_root": str(CUBEMX_ROOT),
                "projects": pm.list_projects()}

    server.tool(
        "project_list",
        "List CubeMX projects known to this server (id, MCU, toolchain, whether a "
        "warm engine is attached and whether a saved .ioc exists).",
        S.obj({}, []), project_list)

    def project_get(args: dict):
        p = pm.get(args["project_id"])
        out = p.meta()
        out["engine_alive"] = p.pid in pm._sessions and pm._sessions[p.pid].alive
        out["has_ioc"] = p.ioc_path.exists()
        if args.get("summary", True) and p.ioc_path.exists():
            out["summary"] = p.ioc().summary()
        return out

    server.tool(
        "project_get",
        "Describe one project: MCU, toolchain, saved .ioc path and (optionally) the "
        "full IOC summary (active IPs, pin count, ProjectManager settings).",
        S.obj({"project_id": S.s("Project id returned by project_create/load"),
               "summary": S.b("Include the parsed .ioc summary", True)},
              ["project_id"]), project_get)

    # -------------------------------------------------------------- create
    def project_create(args: dict):
        name = args["name"]
        pid = pm.new_id(name)
        p = pm.create(pid)
        mcu = args.get("mcu")
        board = args.get("board")
        ioc = args.get("ioc")
        try:
            if ioc:
                path = Path(ioc).expanduser()
                if not path.exists():
                    raise ToolError(f".ioc not found: {path}")
                info = pm.load_ioc(p, path)
                p.toolchain = p.toolchain or ""
            elif board:
                info = pm.load_board(p, board, args.get("board_mode", "nomode"))
            elif mcu:
                info = pm.load_mcu(p, mcu)
            else:
                raise ToolError("provide one of: mcu, board, ioc")
            if args.get("toolchain"):
                r = pm.run(p, f"project toolchain {args['toolchain']}")
                if r["status"] != "OK":
                    raise ToolError(f"toolchain {args['toolchain']!r} rejected: "
                                    f"{r['output'][:200]}")
                p.toolchain = args["toolchain"]
            if args.get("output_dir"):
                p.output_dir = str(Path(args["output_dir"]).expanduser())
            saved = pm.save(p)
        except Exception:
            # keep the project dir for inspection but do not leave a broken engine
            pm.close_engine(p.pid)
            raise
        info.update(saved)
        info["project_id"] = pid
        info["ioc_path"] = str(p.ioc_path)
        return info

    server.tool(
        "project_create",
        "Create a CubeMX project. Give exactly one of `mcu` (part number or db "
        "RefName, e.g. STM32F103C8T6), `board` (e.g. NUCLEO-F030R8) or `ioc` "
        "(existing .ioc to clone). Optionally set toolchain and output_dir. The "
        "project is immediately saved as <workspace>/projects/<id>/project.ioc.",
        S.obj({
            "name": S.s("Human readable project name; becomes the project id slug"),
            "mcu": S.s("MCU part number (STM32F103C8T6) or CubeMX RefName"),
            "board": S.s("Board name (NUCLEO-F030R8)"),
            "board_mode": S.s("Board load mode", ["nomode", "allmodes"], "nomode"),
            "ioc": S.s("Path to an existing .ioc to clone"),
            "toolchain": S.s("Toolchain for generation",
                             ["STM32CubeIDE", "EWARM", "MDK-ARM", "Makefile", "CMake"]),
            "output_dir": S.s("Directory where project generation should write"),
        }, ["name"]), project_create)

    # ---------------------------------------------------------------- open
    def project_open(args: dict):
        pid = args["project_id"]
        p = pm.get(pid)
        ioc = args.get("ioc")
        try:
            if ioc:
                info = pm.load_ioc(p, Path(ioc).expanduser())
            elif p.ioc_path.exists():
                info = pm.load_ioc(p, p.ioc_path)
            elif p.user_mcu:
                info = pm.load_mcu(p, p.user_mcu)
            else:
                raise ToolError(f"project {pid} has no .ioc and no MCU to reload")
        except ToolError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ToolError(str(exc)) from exc
        info["project_id"] = pid
        p.updated = __import__("time").time()
        p.save()
        return info

    server.tool(
        "project_open",
        "Attach a warm CubeMX engine to a known project and reload its .ioc (or a "
        "different .ioc). Needed after a server restart; other tools open lazily too.",
        S.obj({"project_id": S.s("Project id"),
               "ioc": S.s("Optional alternative .ioc to load")},
              ["project_id"]), project_open)

    def project_close(args: dict):
        pid = args["project_id"]
        p = pm.get(pid)
        pm.close_engine(pid)
        p.open = False
        return {"project_id": pid, "engine": "closed"}

    server.tool(
        "project_close",
        "Close the warm engine of a project (frees a JVM; saved .ioc is untouched).",
        S.obj({"project_id": S.s("Project id")}, ["project_id"]), project_close)

    # ---------------------------------------------------------------- save
    def project_save(args: dict):
        p = pm.get(args["project_id"])
        out = pm.save(p, extend=args.get("extended", True))
        out["workspace_dir"] = str(p.dir)
        return out

    server.tool(
        "project_save",
        "Snapshot the live engine configuration into the project .ioc "
        "(config saveas + saveext, so default-valued parameters are persisted too).",
        S.obj({"project_id": S.s("Project id"),
               "extended": S.b("Also write project_ext.ioc with default values", True)},
              ["project_id"]), project_save)

    # ---------------------------------------------------------------- as
    def project_save_as(args: dict):
        src = pm.get(args["project_id"])
        name = args["name"]
        pid = pm.new_id(name)
        dst = pm.create(pid)
        if src.ioc_path.exists():
            import shutil
            shutil.copyfile(src.ioc_path, dst.ioc_path)
            dst.mcu, dst.user_mcu = src.mcu, src.user_mcu
            dst.toolchain = src.toolchain
            dst.save()
            pm.load_ioc(dst, dst.ioc_path)
        else:
            raise ToolError(f"project {src.pid} has no saved .ioc to copy")
        return {"from": src.pid, "project_id": pid, "ioc": str(dst.ioc_path)}

    server.tool(
        "project_save_as",
        "Duplicate a project's saved .ioc into a new project id and open it.",
        S.obj({"project_id": S.s("Source project id"), "name": S.s("New project name")},
              ["project_id", "name"]), project_save_as)

    def project_delete(args: dict):
        pid = args["project_id"]
        p = pm.get(pid)
        pm.close_engine(pid)
        if args.get("remove_files"):
            import shutil
            shutil.rmtree(p.dir, ignore_errors=True)
        pm._projects.pop(pid, None)
        return {"project_id": pid, "files_removed": bool(args.get("remove_files"))}

    server.tool(
        "project_delete",
        "Forget a project; optionally delete its workspace files.",
        S.obj({"project_id": S.s("Project id"),
               "remove_files": S.b("Delete <workspace>/projects/<id>", False)},
              ["project_id"]), project_delete)

    # ---------------------------------------------------------------- diff
    def project_diff(args: dict):
        a = pm.get(args["project_id"]).ioc()
        if args.get("other_project_id"):
            b = pm.get(args["other_project_id"]).ioc()
        elif args.get("other_ioc"):
            from .ioc import IocProject
            b = IocProject.load(args["other_ioc"])
        else:
            raise ToolError("provide other_project_id or other_ioc")
        from .ioc import diff
        d = diff(a, b)
        return {"added": len(d["added"]), "removed": len(d["removed"]),
                "changed": len(d["changed"]), "detail": d}

    server.tool(
        "project_diff",
        "Structural diff between a project's .ioc and another project or .ioc file "
        "(added/removed/changed keys).",
        S.obj({"project_id": S.s("Project id"),
               "other_project_id": S.s("Compare against this project"),
               "other_ioc": S.s("Compare against this .ioc path")},
              ["project_id"]), project_diff)

    # -------------------------------------------------------- mcu / board
    def project_load_mcu(args: dict):
        p = pm.get(args["project_id"])
        out = pm.load_mcu(p, args["mcu"])
        out.update(pm.save(p))
        return out

    server.tool(
        "project_load_mcu",
        "Re-target an existing project to another MCU (CubeMX keeps compatible "
        "pins/peripherals where possible, same as the GUI `load <mcu>`).",
        S.obj({"project_id": S.s("Project id"), "mcu": S.s("MCU part number")},
              ["project_id", "mcu"]), project_load_mcu)

    def project_load_board(args: dict):
        p = pm.get(args["project_id"])
        out = pm.load_board(p, args["board"], args.get("mode", "nomode"))
        out.update(pm.save(p))
        return out

    server.tool(
        "project_load_board",
        "Load a board configuration into a project (default peripherals with "
        "`allmodes`, or bare pinout with `nomode`).",
        S.obj({"project_id": S.s("Project id"), "board": S.s("Board name"),
               "mode": S.s("Board load mode", ["nomode", "allmodes"], "nomode")},
              ["project_id", "board"]), project_load_board)

    # ---------------------------------------------------------- import/export
    def project_export_script(args: dict):
        p = pm.get(args["project_id"])
        target = Path(args.get("path") or (p.dir / "replay.txt"))
        r = pm.run(p, f"export script {target}")
        if r["status"] != "OK" or not target.exists():
            raise ToolError(r["output"][:400] or "export script failed")
        return {"project_id": p.pid, "script": str(target),
                "content": target.read_text(encoding="utf-8", errors="replace")}

    server.tool(
        "project_export_script",
        "Serialize the current configuration into a replayable CubeMX CLI script "
        "(`export script`). This is the exact command list that recreates the project.",
        S.obj({"project_id": S.s("Project id"),
               "path": S.s("Optional output path")},
              ["project_id"]), project_export_script)

    def project_import_config(args: dict):
        p = pm.get(args["project_id"])
        r = pm.run(p, f"import config {Path(args['ioc']).expanduser()}")
        if r["status"] != "OK":
            raise ToolError(r["output"][:400] or "import config failed")
        out = pm.save(p)
        out["imported_from"] = args["ioc"]
        return out

    server.tool(
        "project_import_config",
        "Import another .ioc into the live project (`import config`), then re-save.",
        S.obj({"project_id": S.s("Project id"), "ioc": S.s(".ioc to import")},
              ["project_id", "ioc"]), project_import_config)
