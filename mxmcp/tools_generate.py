"""Project generation, code export and reports."""
from __future__ import annotations

import time
from pathlib import Path

from . import schema as S
from .rpc import ToolError
from .store import ProjectManager

TOOLCHAINS = ["STM32CubeIDE", "EWARM", "MDK-ARM", "Makefile", "CMake"]

# CubeMX prints this when the FW package for the MCU family is not installed.
LOGIN_HINT = "requires prior login"


def _outdir(p, args) -> Path:
    if args.get("output_dir"):
        return Path(args["output_dir"]).expanduser().resolve()
    if p.output_dir:
        return Path(p.output_dir).expanduser().resolve()
    return (p.dir / "generated").resolve()


def _tree(root: Path, limit: int = 400) -> list[str]:
    files = sorted(str(x.relative_to(root)) for x in root.rglob("*") if x.is_file())
    return files[:limit]


def _missing_main(root: Path) -> list[str]:
    """Generation produced drivers but no application code.

    CubeMX reports OK in that case; it happens when the firmware package was
    only resolved late, so just the copy step ran. Re-running generation then
    produces the full project.
    """
    has_main = any(p.name == "main.c" and "Drivers" not in p.parts
                   for p in root.rglob("main.c"))
    has_drv = any("HAL_Driver" in p.parts for p in root.rglob("*"))
    return [] if (has_main or not has_drv) else ["main.c missing while drivers exist"]


def _fw_state(p, args) -> dict:
    """Can `project generate` find a *complete* firmware package?

    CubeMX resolves "STM32Cube FW_F4 V1.28.3" to
    ``~/STM32Cube/Repository/STM32Cube_FW_F4_V1.28.3`` and only checks that the
    directory exists -- interrupted downloads leave a `Projects/`-only folder
    that satisfies that check but has no Drivers, so error hints have to name the
    real reason. A version mismatch (or a missing package) sends the headless
    engine into an interactive download prompt.
    """
    from .firmware import default_repository, scan_repository

    repo = Path(args["repository"]).expanduser() if args.get("repository") \
        else default_repository()
    family = pinned = ""
    reference = ""
    if p.ioc_path.exists():
        ioc = p.ioc()
        family = ioc.family or ""
        pinned = ioc.project_option("FirmwarePackage", "")
        reference = ioc.mcu_name
    marker = family.replace("STM32", "")
    rows = [r for r in scan_repository(repo) if r["family"] == marker]
    installed = [Path(r["path"]).name for r in rows]
    complete = [Path(r["path"]).name for r in rows if r["complete"]]
    want = pinned.split(" V")[-1].strip() if pinned else ""
    base = f"STM32Cube_FW_{marker}_V"
    matching = [r for r in rows if Path(r["path"]).name[len(base):] == want] if want else rows
    good = [Path(r["path"]).name for r in matching if r["complete"]]
    broken = [Path(r["path"]).name for r in matching if not r["complete"]]
    custom = ""
    if p.ioc_path.exists():
        custom = p.ioc().project_option("CustomerFirmwarePackage", "")
    if custom:
        resolved = (p.dir / custom.replace("\\", "/")).resolve()
        custom = str(resolved)
    # An explicit caller path is trusted; otherwise the pinned version must exist
    # in complete form.
    ok = bool(args.get("custom_fw_path")) or bool(good) or bool(not pinned and complete)
    return {"family": family, "mcu": reference, "repository": str(repo),
            "pinned_in_ioc": pinned, "installed": installed,
            "complete": complete, "matching_complete": good,
            "matching_incomplete": broken, "custom_path": custom,
            "available": ok}


def _fw_dir(fw: dict) -> str:
    """Absolute path of the firmware package directory to hand to CubeMX."""
def _fw_dir(fw: dict) -> str:
    """Absolute path of the firmware package directory to hand to CubeMX."""
    for key in ("matching_complete", "compatible"):
        if fw.get(key):
            return str(Path(fw["repository"]) / fw[key][-1])
    if fw.get("complete"):
        return str(Path(fw["repository"]) / fw["complete"][-1])
    if fw.get("installed"):
        return str(Path(fw["repository"]) / fw["installed"][-1])
    return ""


def register(server, pm: ProjectManager) -> None:
    def project_options(args: dict):
        p = pm.get(args["project_id"])
        ioc = p.ioc() if p.ioc_path.exists() else None
        opts = {}
        if ioc:
            opts = {k.split(".", 1)[1]: v for k, v in ioc.entries.items()
                    if k.startswith("ProjectManager.")}
        return {"project_id": p.pid, "options": opts,
                "toolchain_choices": TOOLCHAINS}

    server.tool(
        "project_options",
        "Read the ProjectManager section of the saved .ioc (toolchain, FW package, "
        "heap/stack, file layout, user-code guards...).",
        S.obj({"project_id": S.s("Project id")}, ["project_id"]), project_options)

    def project_set_option(args: dict):
        p = pm.get(args["project_id"])
        results = []
        mapping = {
            "name": "project name", "path": "project path",
            "toolchain": "project toolchain", "compiler": "project compiler",
            "toolchain_location": "project toolchainlocation",
            "couple_files_by_ip": "project couplefilesbyip",
            "generate_under_root": "project generateunderroot",
            "custom_fw_path": "project setCustomFWPath",
            "stack_size": "project set stacksize",
            "heap_size": "project set heapsize",
        }
        for key, cmd in mapping.items():
            val = args.get(key)
            if val is None:
                continue
            if isinstance(val, bool):
                val = "1" if val else "0"
            results.append(pm.run(p, f"{cmd} {val}"))
        if args.get("structure"):
            results.append(pm.run(p, f"SetStructure {args['structure']}"))
        if args.get("copy_library"):
            results.append(pm.run(p, f'SetCopyLibrary "{args["copy_library"]}"'))
        if not results:
            raise ToolError("no option supplied")
        bad = [r for r in results if r["status"] != "OK"]
        if args.get("save", True):
            pm.save(p)
        return {"project_id": p.pid,
                "results": [{"command": r["command"], "status": r["status"],
                             "output": r["output"][:120]} for r in results],
                "failed": [r["command"] for r in bad]}

    server.tool(
        "project_set_option",
        "Set project manager options: name, path, toolchain (STM32CubeIDE/EWARM/"
        "MDK-ARM/Makefile/CMake), compiler (GCC/Starm-Clang), toolchain_location, "
        "couple_files_by_ip, generate_under_root, custom_fw_path, stack_size, "
        "heap_size, structure (Advanced/Basic), copy_library (copy all/copy only/"
        "copy as reference).",
        S.obj({"project_id": S.s("Project id"), "name": S.s("Project name"),
               "path": S.s("Generation root directory"),
               "toolchain": S.s("Toolchain", TOOLCHAINS),
               "compiler": S.s("Compiler/linker", ["GCC", "Starm-Clang"]),
               "toolchain_location": S.s("Explicit toolchain install path"),
               "couple_files_by_ip": S.b("One .c/.h per IP (true) or all in main"),
               "generate_under_root": S.b("Generate under project root"),
               "custom_fw_path": S.s("Custom firmware package path"),
               "stack_size": S.s("Minimum stack size, e.g. 0x800"),
               "heap_size": S.s("Minimum heap size, e.g. 0x400"),
               "structure": S.s("Application structure", ["Advanced", "Basic"]),
               "copy_library": S.s("Library copy mode",
                                   ["copy all", "copy only", "copy as reference"]),
               "save": S.b("Persist the .ioc afterwards", True)},
              ["project_id"]), project_set_option)

    def project_generate(args: dict):
        p = pm.get(args["project_id"])
        outdir = _outdir(p, args)
        outdir.mkdir(parents=True, exist_ok=True)
        toolchain = args.get("toolchain") or p.toolchain or "STM32CubeIDE"
        if toolchain not in TOOLCHAINS:
            raise ToolError(f"unsupported toolchain {toolchain!r}")
        fw = _fw_state(p, args)
        auto_pin = None
        if not fw["available"] and not args.get("allow_download"):
            # Align the pinned version with a *complete* installed package; the
            # custom path is set as well so a reload keeps using the same folder.
            target = (fw["complete"][-1] if fw["complete"] else "")
            if target:
                ver = target.split("_V")[-1]
                spec = f"STM32Cube FW_{fw['family'].replace('STM32','')} V{ver}"
                pm.run(p, f'project setCustomFWPath "{_fw_dir(fw)}"')
                ioc = p.ioc()
                ioc.set_project_option("FirmwarePackage", spec)
                ioc.save(p.ioc_path)
                fw = _fw_state(p, args)
                auto_pin = f"pinned to {spec} (+ custom path)"
            if not fw["available"]:
                bad = fw["matching_incomplete"] or fw["installed"]
                raise ToolError(
                    f"cannot generate for {fw['mcu'] or fw['family'] or '?'}: "
                    f"CubeMX needs firmware package "
                    f"'{fw['pinned_in_ioc'] or '(unset)'}' and "
                    f"{fw['repository']} holds {fw['installed'] or 'nothing'}"
                    + (f" (incomplete - missing Drivers/package.xml: "
                       f"{', '.join(fw['matching_incomplete'] or bad)})"
                       if bad else "")
                    + ". A headless run cannot answer the download dialog. "
                      "Finish the package download in the CubeMX GUI, run "
                      "`swmgr install stm32cube_"
                    + f"{fw['family'].replace('STM32','').lower()}_<version> ask "
                      "(needs a my.st.com login), or pass custom_fw_path to a "
                      "complete local package.")
        name = args.get("name") or p.pid
        steps = []
        steps.append(pm.run(p, f"project toolchain {toolchain}"))
        if args.get("compiler"):
            steps.append(pm.run(p, f'project compiler {args["compiler"]}'))
        steps.append(pm.run(p, f"project name {name}"))
        steps.append(pm.run(p, f"project path {outdir}"))
        if args.get("couple_files_by_ip") is not None:
            steps.append(pm.run(p, "project couplefilesbyip "
                                  f"{1 if args['couple_files_by_ip'] else 0}"))
        if args.get("under_root") is not None:
            steps.append(pm.run(p, "project generateunderroot "
                                  f"{1 if args['under_root'] else 0}"))
        if args.get("custom_fw_path"):
            steps.append(pm.run(p, f'project setCustomFWPath '
                                  f'"{args["custom_fw_path"]}"'))
        if auto_pin and not args.get("custom_fw_path"):
            steps.append(pm.run(p, f'project setCustomFWPath "{_fw_dir(fw)}"'))
        t0 = time.time()
        gen = pm.run(p, "project generate", timeout=args.get("timeout", 300))
        secs = round(time.time() - t0, 1)
        files = _tree(outdir, args.get("max_files", 400))
        if gen.get("hung"):
            # CubeMX is blocked in an interactive step (typically a package
            # download). The engine was restarted by the driver; report what did
            # get written so the caller can decide.
            written = [f for f in files if f.endswith((".c", ".h", ".ioc",
                                                       ".uvprojx", ".project",
                                                       "Makefile", ".ld"))]
            self_note = ("CubeMX stopped responding during generation and was "
                         "restarted. Most likely cause: the firmware package "
                         f"{fw['pinned_in_ioc'] or '(unset)'} is not installed "
                         f"(repository has {fw['installed'] or 'nothing'}) and "
                         "the headless engine cannot complete the download. "
                         "Install it with swmgr, point custom_fw_path at an "
                         "installed package, or set allow_download and login "
                         "first.")
            raise ToolError(self_note + f" Partial output: {written[:20] or 'none'}")
        p.toolchain = toolchain
        p.output_dir = str(outdir)
        saved = pm.save(p)
        login = LOGIN_HINT in (gen["output"] or "")
        if gen["status"] != "OK":
            raise ToolError(
                f"project generate did not complete ({secs}s, status "
                f"{gen['status']}). Output: {gen['output'][:300] or '(none)'}")
        warnings = []
        missing = _missing_main(outdir)
        if missing and args.get("retry_missing_code", True):
            # The package switch takes effect on the next run: regenerate once.
            r2 = pm.run(p, "project generate", timeout=args.get("timeout", 300))
            moved = [f for f in _tree(outdir, 4000) if f.endswith("main.c")
                     and not f.startswith("Drivers")]
            warnings.append("first pass copied drivers only; regenerated and got "
                            + (f"main.c ({r2['seconds']}s)" if moved else
                               "no main.c again"))
            missing = [] if moved else missing
        if missing:
            warnings.append("generators reported OK but application code is "
                            "missing (" + ", ".join(missing) + ")")
        if login:
            warnings.append(
                "CubeMX asked for a my.st.com login to download the firmware "
                "package; install it via swmgr first.")
        files = _tree(outdir, args.get("max_files", 400))
        return {"project_id": p.pid, "toolchain": toolchain, "output_dir": str(outdir),
                "status": gen["status"], "seconds": secs,
                "file_count": len(files), "files": files,
                "firmware": fw, "warnings": warnings, "saved": saved, "firmware_pin": auto_pin,
                "steps": [{"cmd": s["command"], "status": s["status"]} for s in steps]}

    server.tool(
        "project_generate",
        "Generate the complete project (CubeMX code + firmware drivers + IDE "
        "project files) for a toolchain, exactly like `project generate`. "
        "CubeMX may need a my.st.com login to download a missing firmware package; "
        "this is reported in `warnings` with status KO.",
        S.obj({"project_id": S.s("Project id"),
               "output_dir": S.s("Generation root (default project_dir/generated)"),
               "toolchain": S.s("Toolchain", TOOLCHAINS),
               "compiler": S.s("Compiler/linker", ["GCC", "Starm-Clang"]),
               "name": S.s("Project name used for the generated project"),
               "couple_files_by_ip": S.b("One file per IP"),
               "under_root": S.b("Generate files under the project root"),
               "custom_fw_path": S.s("Alternative firmware package path"),
               "repository": S.s("Override the firmware repository path"),
               "allow_download": S.b("Let CubeMX attempt a headless download "
                                     "(can stall; install the package instead)",
                                     False),
               "timeout": S.i("Generation timeout in seconds", 1800, 60, 7200),
               "retry_missing_code": S.b("Regenerate once when only drivers were copied", True),
               "max_files": S.i("Max paths to list", 400, 1, 5000)},
              ["project_id"]), project_generate)

    def generate_code(args: dict):
        p = pm.get(args["project_id"])
        outdir = Path(args.get("output_dir") or (p.dir / "code")).expanduser().resolve()
        outdir.mkdir(parents=True, exist_ok=True)
        if args.get("mode") == "all_in_main":
            pm.run(p, "generate all_code_in_main")
        elif args.get("mode") == "one_file_per_ip":
            pm.run(p, "generate one_file_per_ip")
        r = pm.run(p, f"generate code {outdir}", timeout=1800)
        if r["status"] != "OK":
            raise ToolError(r["output"][:400] or "generate code failed")
        files = _tree(outdir)
        return {"project_id": p.pid, "output_dir": str(outdir),
                "file_count": len(files), "files": files}

    server.tool(
        "generate_code",
        "Generate only the CubeMX application code into a directory "
        "(`generate code <dir>`, no drivers/IDE files). `mode` may force the "
        "all-in-main or one-file-per-IP layout first.",
        S.obj({"project_id": S.s("Project id"),
               "output_dir": S.s("Destination directory"),
               "mode": S.s("Optional layout override",
                           ["", "all_in_main", "one_file_per_ip"])},
              ["project_id"]), generate_code)

    def project_csv(args: dict):
        p = pm.get(args["project_id"])
        target = Path(args.get("path") or (p.dir / "pinout.csv")).expanduser().resolve()
        r = pm.run(p, f"csv pinout {target}")
        if r["status"] != "OK":
            raise ToolError(r["output"][:300] or "csv pinout failed")
        return {"project_id": p.pid, "csv": str(target),
                "preview": target.read_text(encoding="utf-8", errors="replace")[:2000]
                if target.exists() else ""}

    server.tool(
        "project_csv",
        "Export the current pin configuration to CSV (`csv pinout <file>`), the "
        "same file the GUI passes to board layout tools.",
        S.obj({"project_id": S.s("Project id"), "path": S.s("CSV output path")},
              ["project_id"]), project_csv)

    def project_report(args: dict):
        """Reports: CubeMX exposes its HTML/text report through the project manager
        plugin (GUI only); the MCP reproduces it from the .ioc so it also works
        headless."""
        p = pm.get(args["project_id"])
        ioc = p.ioc() if p.ioc_path.exists() else None
        if ioc is None:
            pm.save(p)
            ioc = p.ioc()
        lines = ["STM32CubeMX project report", "=" * 40, ""]
        lines += [f"Project       : {p.pid}", f"MCU           : {ioc.mcu_name}",
                  f"Part number   : {ioc.mcu_cpn}", f"Package       : {ioc.mcu_package}",
                  f"Family        : {ioc.family}",
                  f"CubeMX        : {ioc.cube_version} ({ioc.db_version})", ""]
        lines.append("Active IPs:")
        for ip in ioc.ips:
            lines.append(f"  - {ip}: {ioc.get(ip + '.IPParameters')}")
        lines += ["", "Pins:"]
        for pin in ioc.pins:
            st = ioc.pin_state(pin)
            lines.append(f"  {pin:24s} {st.signal:20s} {st.label}")
        lines += ["", "RCC:"]
        for name in ioc.ip_parameters("RCC"):
            lines.append(f"  {name} = {ioc.get_ip_param('RCC', name)}")
        lines += ["", "Project manager:"]
        for k in sorted(ioc.entries):
            if k.startswith("ProjectManager."):
                lines.append(f"  {k.split('.', 1)[1]} = {ioc.entries[k]}")
        text = "\n".join(lines)
        target = Path(args.get("path") or (p.dir / "report.txt"))
        target.write_text(text, encoding="utf-8")
        return {"project_id": p.pid, "report": str(target), "text": text[:4000]}

    server.tool(
        "project_report",
        "Produce a human readable report of the configuration (MCU, active IPs, "
        "pin map, clock settings, project settings) from the saved .ioc.",
        S.obj({"project_id": S.s("Project id"),
               "path": S.s("Report output path")},
              ["project_id"]), project_report)

    def project_files(args: dict):
        p = pm.get(args["project_id"])
        root = Path(args.get("root") or p.output_dir or (p.dir / "generated"))
        if not root.exists():
            raise ToolError(f"directory does not exist: {root}")
        files = sorted(root.rglob(args.get("glob", "*")))
        rows = [{"path": str(f.relative_to(root)), "size": f.stat().st_size}
                for f in files if f.is_file()][: args.get("limit", 300)]
        return {"root": str(root), "count": len(rows), "files": rows}

    server.tool(
        "project_files",
        "List generated files under the project output directory (glob filter).",
        S.obj({"project_id": S.s("Project id"), "root": S.s("Override root"),
               "glob": S.s("Glob, default *", "*"),
               "limit": S.i("Max rows", 300, 1, 5000)},
              ["project_id"]), project_files)




