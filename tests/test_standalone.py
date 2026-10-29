"""End-to-end test of the standalone (no CubeMX) path.

Runs the MCP server with MXMCP_CUBEMX_ROOT pointed at a non-existent directory,
so any hidden dependency on the installation surfaces immediately.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "build" / "noinstall"
if WORK.exists():
    shutil.rmtree(WORK, ignore_errors=True)
WORK.mkdir(parents=True)

env = dict(os.environ)
env["MXMCP_CUBEMX_ROOT"] = str(WORK / "no-such-cubemx")
env["MXMCP_WORKSPACE"] = str(WORK / "ws")
env["PYTHONIOENCODING"] = "utf-8"

proc = subprocess.Popen([sys.executable, "-m", "mxmcp.server"],
                        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL, cwd=str(ROOT), text=True,
                        encoding="utf-8", env=env)
_id = 0


def rpc(method, params=None):
    global _id
    _id += 1
    req = {"jsonrpc": "2.0", "id": _id, "method": method}
    if params is not None:
        req["params"] = params
    proc.stdin.write(json.dumps(req) + "\n")
    proc.stdin.flush()
    while True:
        line = proc.stdout.readline()
        if not line:
            raise SystemExit("server closed")
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if msg.get("id") == _id:
            if "error" in msg:
                raise RuntimeError(msg["error"])
            return msg["result"]


def call(tool, **args):
    res = rpc("tools/call", {"name": tool, "arguments": args})
    text = res["content"][0]["text"]
    if res.get("isError"):
        return {"__error__": text[:300]}
    return json.loads(text)


def main() -> int:
    rpc("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                       "clientInfo": {"name": "sa", "version": "1"}})
    tools = rpc("tools/list")["tools"]
    print(f"tools: {len(tools)}")

    info = call("standalone_info")
    print("mode:", info["mode"], "| engine:", info["engine_available"],
          "| pack:", info["pack_present"], info.get("pack_bytes"))
    print("counts:", info["counts"])
    assert info["mode"] == "standalone" and info["pack_present"]

    r = call("standalone_mcu", query="STM32F103C8")
    print("search:", r["count"], [m["ref_name"] for m in r["mcus"][:3]])

    p = call("standalone_create", name="sa_e2e", mcu="STM32F103C8T6")
    pid = p["project_id"]
    print("create:", p["mcu"], p["package"], "pins:", p["pins"])

    s = call("standalone_signals", project_id=pid, pin="PA9")
    print("PA9 signals:", s["signals"][:6])

    print("pin:", call("standalone_pin", project_id=pid, pin="PA9",
                       signal="USART1_TX").get("signal"))
    print("pin:", call("standalone_pin", project_id=pid, pin="PA10",
                       signal="USART1_RX").get("signal"))
    print("pin:", call("standalone_pin", project_id=pid, pin="PC13",
                       signal="GPIO_Output").get("signal"))
    bad = call("standalone_pin", project_id=pid, pin="PA9",
               signal="USART3_TX")
    print("invalid pin signal rejected:", "__error__" in bad)

    print("mode:", call("standalone_mode", project_id=pid, ip="USART1",
                        mode="Asynchronous").get("registered"))
    print("param:", call("standalone_param", project_id=pid, ip="USART1",
                         param="BaudRate", value="115200").get("registered"))
    print("nvic:", call("standalone_nvic", project_id=pid, irq="USART1_IRQn",
                        priority=1, enabled=True).get("enabled"))

    v = call("standalone_validate", project_id=pid)
    print("validate ok:", v["ok"], v["problems"])

    g = call("standalone_generate", project_id=pid,
             output_dir=str(WORK / "gen"), name="sa_e2e")
    print("generate:", g["file_count"], "files", g["fidelity"])
    main_c = (Path(g["outdir"]) / "Core" / "Src" / "main.c")
    text = main_c.read_text(encoding="utf-8")
    print("main.c bytes:", len(text),
          "| BaudRate line:", any("BaudRate = 115200" in l
                                  for l in text.splitlines()))

    # engine-only tools must fail cleanly, not crash
    e = call("project_create", name="x", mcu="STM32F103C8T6")
    print("engine tool without install -> clean error:", "__error__" in e,
          str(e)[:110])
    proc.stdin.close()
    proc.terminate()
    return 0


if __name__ == "__main__":
    sys.exit(main())
