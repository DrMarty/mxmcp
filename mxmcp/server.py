"""Entry point: build the MCP server and serve JSON-RPC over stdio.

Usage:
    python -m mxmcp.server                # MCP stdio server
    python -m mxmcp.server --selftest     # start, call initialize/tools/list, exit
    python -m mxmcp.server --call NAME --args '{"project_id": "..."}'

Environment:
    MXMCP_WORKSPACE     where project state lives        (default ~/.mxmcp)
    MXMCP_CUBEMX_ROOT   CubeMX installation              (default Program Files)
    MXMCP_MAX_ENGINES   warm JVMs to keep                (default 3)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback

from . import __version__
from .rpc import McpServer
from .store import ProjectManager

INSTRUCTIONS = """\
STM32CubeMX control server.

Typical flow
  1. project_create {name, mcu|board|ioc}      -> project_id
  2. mcu_pin_functions / pin_functions         -> legal signals for a pin
  3. pin_set / mode_set / ip_param_set / clock_set
  4. project_save                              -> project.ioc snapshot
  5. project_generate {toolchain, output_dir}  -> full IDE project
Supporting tools: catalog_index, mcu_search, mcu_info, board_search,
peripheral_list, mode_list, ip_params_dump, gpio_params, pack_status, swmgr,
project_report, project_csv, project_export_script, verify, cli, cli_batch.

Notes
  * A project maps to one warm CubeMX JVM; keep the number of open projects small.
  * CubeMX only persists IP parameters that are listed in <IP>.IPParameters; the
    parameter tools take care of that automatically.
  * Generating a project for a family whose firmware package is not installed
    requires a my.st.com login (reported as a warning, not a crash).
"""


def build_server(pm: ProjectManager) -> McpServer:
    srv = McpServer("mxmcp", __version__, INSTRUCTIONS)
    from . import (
        tools_advanced,
        tools_catalog,
        tools_cli,
        tools_clock,
        tools_generate,
        tools_middleware,
        tools_pack,
        tools_pins,
        tools_project,
        tools_rtos,
        tools_standalone,
    )
    tools_project.register(srv, pm)
    tools_catalog.register(srv, pm)
    tools_pins.register(srv, pm)
    tools_clock.register(srv, pm)
    tools_generate.register(srv, pm)
    tools_pack.register(srv, pm)
    tools_cli.register(srv, pm)
    tools_advanced.register(srv, pm)
    tools_rtos.register(srv, pm)
    tools_middleware.register(srv, pm)
    tools_standalone.register(srv, pm)

    def _readme() -> str:
        path = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "README.md")
        try:
            return open(path, encoding="utf-8").read()
        except OSError:
            return "README unavailable"

    def _cli_reference() -> str:
        path = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "docs", "CLI_REFERENCE.md")
        try:
            return open(path, encoding="utf-8").read()
        except OSError:
            return "CLI reference unavailable"

    srv.resource("mxmcp://docs/readme", "README", "Server overview and tool list",
                 _readme)
    srv.resource("mxmcp://docs/cli-reference", "CLI reference",
                 "Complete CubeMX command language notes", _cli_reference)
    return srv


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="mxmcp")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--call", help="invoke one tool and print the result")
    ap.add_argument("--args", default="{}")
    ap.add_argument("--list-tools", action="store_true")
    ap.add_argument("--workspace")
    ap.add_argument("--cubemx-root")
    ap.add_argument("--max-engines", type=int, default=3)
    ns = ap.parse_args(argv)

    if ns.workspace:
        os.environ["MXMCP_WORKSPACE"] = ns.workspace
    if ns.cubemx_root:
        os.environ["MXMCP_CUBEMX_ROOT"] = ns.cubemx_root

    global WORKSPACE, CUBEMX_ROOT
    from . import store as store_mod
    if ns.workspace:
        store_mod.WORKSPACE = WORKSPACE = __import__("pathlib").Path(ns.workspace)
    if ns.cubemx_root:
        store_mod.CUBEMX_ROOT = CUBEMX_ROOT = __import__("pathlib").Path(ns.cubemx_root)

    pm = ProjectManager(max_open=ns.max_engines)
    srv = build_server(pm)

    try:
        if ns.list_tools:
            for name, spec in sorted(srv.tools.items()):
                print(f"{name:28s} {spec['description'].splitlines()[0][:100]}")
            print(f"\n{len(srv.tools)} tools")
            return 0
        if ns.call:
            reply = srv.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                "params": {"name": ns.call,
                                           "arguments": json.loads(ns.args)}})
            print(json.dumps(reply, indent=1, ensure_ascii=False))
            return 0
        if ns.selftest:
            init = srv.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                               "params": {"protocolVersion": "2024-11-05",
                                          "capabilities": {},
                                          "clientInfo": {"name": "selftest",
                                                         "version": "0"}}})
            tools = srv.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
            print(json.dumps(init["result"]["serverInfo"], indent=1))
            print(f"tools: {len(tools['result']['tools'])}")
            return 0
        srv.serve()
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        return 1
    finally:
        pm.close_all()


if __name__ == "__main__":
    sys.exit(main())
