"""Verify middleware tools end-to-end (list, enable FATFS, report active IPs)."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "build" / "mwtest"
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
    text = res["content"][0]["text"]
    if res.get("isError"):
        return {"__error__": text[:400]}
    return json.loads(text)


def main() -> int:
    rpc("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                       "clientInfo": {"name": "mw", "version": "1"}})
    print("tools:", len(rpc("tools/list")["tools"]))

    p = call("project_create", name="MW1", mcu="STM32F103C8T6",
             toolchain="Makefile")
    pid = p["project_id"]
    r = call("middleware_list")
    print("known:", len(r["known_middleware"]),
          r["known_middleware"][:8])
    print("custom hint:", r["custom_middleware"][:60])

    r = call("middleware_add", project_id=pid, name="FREERTOS", mode="CMSIS_V2")
    print("enable FREERTOS:", r.get("status"), r.get("ips"))

    r = call("middleware_add", project_id=pid, name="FATFS", mode="FATFS")
    print("enable FATFS:", r.get("status") or r.get("__error__", "")[:140],
          r.get("ips"))

    r = call("middleware_list", project_id=pid)
    print("active:", r["active_in_project"])

    r = call("rtos_status", project_id=pid)
    print("rtos:", r.get("mode"), r.get("objects"))

    r = call("verify", project_id=pid)
    print("verify:", r.get("ok"), (r.get("problems") or [])[:2])
    proc.stdin.close()
    proc.terminate()
    return 0


if __name__ == "__main__":
    sys.exit(main())
