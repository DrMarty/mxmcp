"""End-to-end test: MCP JSON-RPC over stdio, real CubeMX engine.

Spawns `python -m mxmcp.server` exactly like an MCP client, then drives a full
flow: create project from a part number, configure pins/peripheral/clock, save,
generate, verify. Any failure surfaces the tool error text.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "build" / "mcp_test"


class Client:
    def __init__(self, workspace: Path) -> None:
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "mxmcp.server", "--workspace", str(workspace)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=str(ROOT), env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        self.next_id = 1

    def rpc(self, method: str, params: dict | None = None) -> dict:
        msg = {"jsonrpc": "2.0", "id": self.next_id, "method": method}
        if params is not None:
            msg["params"] = params
        self.next_id += 1
        self.proc.stdin.write((json.dumps(msg) + "\n").encode())
        self.proc.stdin.flush()
        while True:
            line = self.proc.stdout.readline()
            if not line:
                err = self.proc.stderr.read().decode("utf-8", "replace")
                raise RuntimeError(f"server died:\n{err[-3000:]}")
            reply = json.loads(line.decode())
            if reply.get("id") == msg["id"]:
                return reply

    def call(self, tool_name: str, **args) -> dict:
        t0 = time.time()
        reply = self.rpc("tools/call", {"name": tool_name, "arguments": args})
        res = reply.get("result", {})
        text = res.get("content", [{}])[0].get("text", "")
        print(f"  [{tool_name} {time.time()-t0:5.1f}s]", flush=True)
        if res.get("isError"):
            raise RuntimeError(f"{tool_name} failed:\n{text[:2500]}")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"text": text}

    def close(self) -> None:
        try:
            self.proc.stdin.close()
        except Exception:
            pass
        try:
            self.proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            self.proc.kill()


def main() -> int:
    shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True, exist_ok=True)
    c = Client(WORK)
    t0 = time.time()
    init = c.rpc("initialize", {"protocolVersion": "2024-11-05",
                                "capabilities": {},
                                "clientInfo": {"name": "e2e", "version": "1"}})
    print("initialize ->", init["result"]["serverInfo"])
    tools = c.rpc("tools/list")["result"]["tools"]
    print("tools:", len(tools))

    print("\n# catalog")
    print("index:", c.call("catalog_index")["mcu_count"], "MCUs",
          c.call("catalog_index")["board_count"], "boards")
    print("search:", [m["ref_name"] for m in c.call("mcu_search", query="STM32F103C8T6")["matches"]])
    print("board:", [b["name"] for b in c.call("board_search", query="NUCLEO-F030")["matches"]])

    print("\n# create")
    proj = c.call("project_create", name="E2E_F103", mcu="STM32F103C8T6",
                  toolchain="Makefile")
    pid = proj["project_id"]
    print("project:", pid, proj.get("mcu"), proj.get("ioc"))

    print("\n# configure")
    print("functions PA9:", c.call("pin_functions", project_id=pid,
                                   pin="PA9")["functions"][:4])
    c.call("pin_set", project_id=pid, pin="PC13", signal="GPIO_Output")
    c.call("pin_set", project_id=pid, pin="PA9", signal="USART1_TX")
    c.call("pin_set", project_id=pid, pin="PA10", signal="USART1_RX")
    print("mode:", c.call("mode_set", project_id=pid, peripheral="USART1",
                          mode="Asynchronous"))
    print("ip param:", c.call("ip_param_set", project_id=pid, ip="USART1",
                              param="BaudRate", value="115200"))
    print("clock:", c.call("clock_set", project_id=pid, sysclk_hz=72000000,
                           pll_mul="RCC_PLL_MUL9",
                           pll_source="RCC_PLLSOURCE_HSE",
                           sysclk_source="RCC_SYSCLKSOURCE_PLLCLK",
                           apb1_div="RCC_HCLK_DIV2")["applied"])
    print("gpio label:", c.call("gpio_set", project_id=pid, pin="PC13",
                                param="GPIO_Label", value="LED"))

    print("\n# save + verify")
    saved = c.call("project_save", project_id=pid)
    print("saved:", saved["ioc"], "mcu", saved["mcu"])
    print("pinout:", [p for p in c.call("pinout_get", project_id=pid)["pins"]
                      if p["signal"] not in ("Reset_State", "Power")])
    v = c.call("verify", project_id=pid)
    print("verify ok:", v["ok"], "problems:", v["problems"])

    print("\n# generate")
    gen = c.call("project_generate", project_id=pid, output_dir=str(WORK / "gen"),
                 max_files=60)
    print("generate:", gen["status"], gen["file_count"], "files",
          "warnings:", gen["warnings"])
    print("sample:", gen["files"][:8])

    print("\n# report / csv / replay")
    print("csv rows:", len(c.call("project_csv", project_id=pid)["preview"].splitlines()))
    rep = c.call("project_report", project_id=pid)
    print("report head:", rep["text"].splitlines()[:3])
    script = c.call("project_export_script", project_id=pid)
    print("replay lines:", len(script["content"].splitlines()))

    print("\n# board project (NUCLEO-F030R8, allmodes)")
    bd = c.call("project_create", name="E2E_NUCLEO", board="NUCLEO-F030R8",
                board_mode="allmodes")
    bid = bd["project_id"]
    pins = c.call("pinout_get", project_id=bid)["pins"]
    print("board mcu:", bd.get("mcu"), "configured pins:",
          len([p for p in pins if p["signal"] not in ("Reset_State", "Power")]))

    print("\n# second MCU family (STM32F407VGT6) + clock + generate")
    f4 = c.call("project_create", name="E2E_F407", mcu="STM32F407VGT6",
                toolchain="Makefile")
    fid = f4["project_id"]
    c.call("pin_set", project_id=fid, pin="PA9", signal="USART1_TX")
    c.call("pin_set", project_id=fid, pin="PA10", signal="USART1_RX")
    c.call("mode_set", project_id=fid, peripheral="USART1", mode="Asynchronous")
    clk = c.call("clock_set", project_id=fid, sysclk_hz=168000000,
                 pll_mul="RCC_PLL_MUL8", pll_source="RCC_PLLSOURCE_HSE",
                 hse_pins=["PH0", "PH1"],
                 sysclk_source="RCC_SYSCLKSOURCE_PLLCLK")
    derived = clk.get("derived_frequencies", {})
    print("clock PLL/VCO:", derived.get("PLLCLKFreq_Value"),
          derived.get("VCOOutputFreq_Value"), "routed:", len(clk.get("hse_routed") or []),
          clk.get("warning") or "")
    try:
        g4 = c.call("project_generate", project_id=fid,
                    output_dir=str(WORK / "gen_f4"), max_files=10)
        print("F4 generate:", g4["status"], g4["file_count"], "files",
              "warnings:", g4["warnings"])
    except RuntimeError as exc:
        # F4 firmware on this machine is a Projects/-only leftover; the tool is
        # expected to refuse fast with an actionable message.
        msg = str(exc)
        ok = "incomplete" in msg and "custom_fw_path" in msg
        print("F4 generate refused (expected):", "OK" if ok else "UNEXPECTED")
        if not ok:
            raise

    print("\n# raw CLI bridge")
    raw = c.call("cli", project_id=pid, command="get mcu peripherals")
    print("cli lines:", len(raw["output"].splitlines()), raw["status"])

    c.close()
    print(f"\nTOTAL {time.time()-t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())



