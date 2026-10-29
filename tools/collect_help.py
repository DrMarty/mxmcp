"""Collect help text for every supported CubeMX CLI root command.

`help <cmd>` always prints the global usage table, so for sub-commands we call
the bare root (which prints its own usage block) and keep everything from the
first "Usage:" line. Results land in docs/cli_help/<cmd>.txt.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mx_harness import run_mx  # noqa: E402

ROOTS = [
    "log", "set", "import", "ocxtest", "MultiConfig", "load", "get", "lock",
    "reset", "clearpinout", "possible_value", "not_a_possible_value", "add",
    "check", "csv", "generate", "tinyload", "waitclock", "switch", "unset",
    "export", "list", "loadboard", "project", "setDriver", "SetStructure",
    "SetCopyLibrary", "pinout", "disable", "login", "logout", "login_with_gui",
    "tooltip", "clock", "updateIpUI", "swmgr", "config", "cpload", "cpexport",
    "user_analytics", "simulate", "isPluginError", "exit_mx", "setprop",
    "getprop", "getenv", "xcopy", "xts", "xtest", "xbuild", "popupwrapper",
    "xcubedl", "help", "exit", "script", "dma", "NVIC", "pack",
]

SUB = {
    "NVIC": ["NVIC enable", "NVIC disable", "NVIC set_priority",
             "NVIC set_subpriority", "NVIC set_prioritygroup", "NVIC get"],
    "dma": ["dma add", "dma remove", "dma list", "dma config"],
    "clock": ["clock resolution", "clock get", "clock set"],
    "pinout": ["pinout check keep user placement"],
    "pack": ["pack enable", "pack disable", "pack status", "pack validate",
             "pack context", "pack migrate"],
    "swmgr": ["swmgr refresh", "swmgr install", "swmgr remove",
              "swmgr connection check", "swmgr connection status",
              "swmgr getSelectedDB", "swmgr set repository",
              "swmgr set proxy type", "swmgr hello"],
    "project": ["project generate", "project name", "project path",
                "project toolchain", "project compiler",
                "project couplefilesbyip", "project generateunderroot",
                "project setCustomFWPath", "project toolchainlocation",
                "project get stacksize", "project set stacksize",
                "project get heapsize", "project set heapsize",
                "project import", "project save"],
    "config": ["config load", "config save", "config saveas", "config saveext"],
    "csv": ["csv pinout"],
    "generate": ["generate code"],
    "export": ["export script"],
    "get": ["get modes", "get mapped modes", "get mode", "get mode_param_list",
            "get mode_param_possvalue", "get mode_param_pattern",
            "get available modes", "get signal", "get pinout",
            "get gpio parameters", "get ip parameters", "get mcu name",
            "get mcu package", "get mcu peripherals", "get functions",
            "get possible remaps", "get sub-modes", "get sub-mode-state",
            "get available-analog-signals", "get codegeneratormode",
            "get bsp status", "get version", "get tpl_path", "get dest_path"],
    "set": ["set mode", "set pin", "set pinreservation", "set gpio parameters",
            "set ip parameters", "set ip MMTControlled", "set ip no_ui_warning",
            "set username", "set AllIpInContext", "set contextProject",
            "set context", "set userconst", "set bsp", "set noparam"],
    "add": ["add mw"],
    "check": ["check mode enabled", "check mcu modes"],
    "list": ["list ipdependencies"],
    "import": ["import config", "import add_compatibility_rule"],
}

OUT = Path(__file__).resolve().parent.parent / "docs" / "cli_help"
OUT.mkdir(parents=True, exist_ok=True)


def clean_block(out: list[str], marker: str) -> str:
    """Keep the response that follows the echoed command."""
    text = "\n".join(out)
    idx = text.find(marker)
    if idx < 0:
        return text[-2000:]
    body = text[idx + len(marker):]
    body = body.split("\nBye bye")[0]
    return body.strip("\n")


def main() -> int:
    work = Path(__file__).resolve().parent.parent / "probe" / "helpscan"
    results = {}
    lines = [c for c in ROOTS] + [s for v in SUB.values() for s in v]
    for cmd in lines:
        rc, out = run_mx(work, [cmd, "exit"], timeout=120)
        block = clean_block(out, cmd)
        safe = cmd.replace(" ", "_").replace("/", "_")
        (OUT / f"{safe}.txt").write_text(block, encoding="utf-8")
        results[cmd] = block
        print(f"[{cmd}] {len(block)} chars", file=sys.stderr)
    (Path(__file__).resolve().parent.parent / "docs" / "cli_help.json").write_text(
        json.dumps(results, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
