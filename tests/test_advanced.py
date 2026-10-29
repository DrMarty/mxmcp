"""End-to-end check of the tools added by the deep RE pass.

Runs through the real MCP surface (stdio JSON-RPC) so every new tool is proven to
register, execute and return parseable data. Prints one line per tool.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "build" / "adv"
if WORK.exists():
    shutil.rmtree(WORK, ignore_errors=True)
WORK.mkdir(parents=True)

proc = subprocess.Popen([sys.executable, "-m", "mxmcp.server"],
                        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL, cwd=str(ROOT), text=True,
                        encoding="utf-8")
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
    if res.get("isError"):
        text = res["content"][0]["text"]
        return {"__error__": text[:300]}
    return json.loads(res["content"][0]["text"])


def show(label, obj, keys=None):
    if isinstance(obj, dict) and "__error__" in obj:
        print(f"FAIL {label}: {obj['__error__'][:150]}")
        return False
    if keys:
        vals = {k: (str(obj.get(k))[:70] if not isinstance(obj.get(k), (list, dict))
                    else f"<{len(obj.get(k))}>") for k in keys}
        print(f"ok   {label}: {vals}")
    else:
        print(f"ok   {label}: {str(obj)[:140]}")
    return True


def main() -> int:
    rpc("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                       "clientInfo": {"name": "adv", "version": "1"}})
    tools = rpc("tools/list")["tools"]
    print(f"tools registered: {len(tools)}")
    ok = True

    p = call("project_create", name="ADV1", mcu="STM32F103C8T6", toolchain="Makefile")
    pid = p["project_id"]
    ok &= show("project_create", p, ["project_id", "mcu"])

    call("pin_set", project_id=pid, pin="PA2", signal="USART2_TX")
    call("pin_set", project_id=pid, pin="PA3", signal="USART2_RX")
    call("mode_set", project_id=pid, peripheral="USART2", mode="Asynchronous")

    r = call("nvic_write", project_id=pid, action="enable", irq="USART2_IRQn")
    ok &= show("nvic_write enable USART2_IRQn", r, ["status", "command"])
    r = call("nvic_write", project_id=pid, action="set_priority", irq="USART2_IRQn",
             value=1)
    ok &= show("nvic_write set_priority", r, ["status"])
    r = call("nvic_read", project_id=pid, action="get_priority", irq="USART2_IRQn")
    ok &= show("nvic_read get_priority", r, ["values", "text"])
    r = call("nvic_read", project_id=pid, action="get_interrupts")
    ok &= show("nvic_read get_interrupts", r, ["count"])
    r = call("nvic_read", project_id=pid, action="get_ip_interrupts", irq="USART2")
    ok &= show("nvic_read get_ip_interrupts", r, ["interrupts"])
    r = call("nvic_read", project_id=pid, action="get_prioritygroup")
    ok &= show("nvic_read prioritygroup", r, ["priority_group"])
    r = call("nvic_read", project_id=pid, action="get_enable_state",
             irq="USART2_IRQn")
    ok &= show("nvic_read get_enable_state", r, ["values"])
    r = call("nvic_read", project_id=pid, action="get_usesfreertosfunctions")
    ok &= show("nvic_read usesfreertosfunctions", r, ["text", "status"])
    r = call("nvic_write", project_id=pid, action="set_irqhandlergenerated",
             irq="USART2_IRQn", value="true")
    ok &= show("nvic_write set_irqhandlergenerated", r, ["status"])

    r = call("dma_query", project_id=pid, action="list_all")
    ok &= show("dma_query list_all", r, ["status", "items"])
    r = call("dma_query", project_id=pid, action="available_periph_requests",
             target="USART2")
    ok &= show("dma_query available_periph_requests", r, ["items"])
    r = call("dma_query", project_id=pid, action="available_controller_requests",
             target="DMA1")
    ok &= show("dma_query available_controller_requests", r, ["items"])
    r = call("dma_mutate", project_id=pid, kind="add", request="USART2_RX")
    ok &= show("dma_mutate add USART2_RX", r, ["status", "command"])
    r = call("dma_query", project_id=pid, action="list", target="USART2_RX")
    ok &= show("dma_query list USART2_RX", r, ["items"])
    r = call("dma_mutate", project_id=pid, kind="delete", request="USART2_RX")
    ok &= show("dma_mutate delete", r, ["status"])

    r = call("mdma_query", project_id=pid, action="list_all_requests")
    ok &= show("mdma_query (F1 has no MDMA -> KO expected)", r, ["status"])

    r = call("gic_query", project_id=pid, action="get_interrupts")
    ok &= show("gic_query on F1 (KO expected)", r, ["status"])

    r = call("mmt", project_id=pid, action="dump", target="free")
    ok &= show("mmt dump free (F1 lacks MMT)", r, ["status", "note"])

    r = call("value_check", project_id=pid, ip="USART2", parameter="BaudRate",
             value="115200")
    ok &= show("value_check", r, ["is_possible", "is_not_possible", "current"])
    r = call("value_check", project_id=pid, ip="USART2", parameter="WordLength",
             value="0x800")
    ok &= show("value_check hex param", r, ["is_possible", "current"])

    r = call("mode_pattern", project_id=pid, ip="USART2", mode="Asynchronous",
             parameter="BaudRate")
    ok &= show("mode_pattern", r, ["pattern", "status"])
    r = call("submode_state", project_id=pid, ip="USART2", path="Asynchronous")
    ok &= show("submode_state", r, ["state", "children"])

    r = call("lpbam", project_id=pid, action="list")
    ok &= show("lpbam list", r, ["status", "text"])

    r = call("ide_bridge", project_id=pid, action="codegenerator_mode")
    ok &= show("ide_bridge codegenerator_mode", r, ["text"])
    r = call("ide_bridge", project_id=pid, action="ip_dependencies")
    ok &= show("ide_bridge ip_dependencies", r, ["status"])
    r = call("ide_bridge", project_id=pid, action="is_plugin_error", plugin="RCC")
    ok &= show("ide_bridge is_plugin_error", r, ["text", "status"])

    r = call("compliance", project_id=pid, action="check_modes")
    ok &= show("compliance check_modes", r, ["problem_count"])
    r = call("compliance", project_id=pid, action="check_mode", ip="USART2",
             mode="Asynchronous")
    ok &= show("compliance check_mode", r, ["text"])

    r = call("porting", project_id=pid, action="report", report="rep.txt")
    ok &= show("porting report", r, ["status", "command"])
    r = call("porting", project_id=pid, action="set_option", option="Keep Pin State",
             value="true")
    ok &= show("porting set_option", r, ["status", "command"])

    r = call("command_catalog", command="dma")
    ok &= show("command_catalog dma", r, ["matches"])
    r = call("command_catalog")
    ok &= show("command_catalog total", r, ["total", "jars"])

    r = call("product_db", search="STM32F103")
    ok &= show("product_db search", r, ["matches_by_table"] if isinstance(r, dict) and "matches_by_table" in r else ["__error__"] if "__error__" in r else ["database"])

    r = call("runtime_props", action="getprop", name="user.home")
    ok &= show("runtime_props getprop", r, ["text"])

    r = call("selectors", project_id=pid, kind="selector", action="list mcus")
    ok &= show("selectors list mcus", r, ["status", "note"])
    r = call("selectors", project_id=pid, kind="boardselector", action="list boards")
    ok &= show("boardselector list boards", r, ["status", "note"])

    print("ALL OK" if ok else "SOME FAILURES")
    proc.stdin.close()
    proc.terminate()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
