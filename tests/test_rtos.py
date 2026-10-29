"""Verify the RTOS tools against a real FreeRTOS project."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "build" / "rtos"
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
                       "clientInfo": {"name": "rtos", "version": "1"}})
    print("tools:", len(rpc("tools/list")["tools"]))

    p = call("project_create", name="RTOS1", mcu="STM32F103C8T6",
             toolchain="Makefile")
    pid = p["project_id"]
    print("project:", pid, p["mcu"])

    sch = call("rtos_schema")
    print("schema apis:", [(a["api"], len(a["objects"])) for a in sch["apis"]])
    v2 = next(a for a in sch["apis"] if a["api"] == "CMSIS RTOS2")
    print("v2 objects:", [o["object"] for o in v2["objects"]])
    tasks = next(o for o in v2["objects"] if o["id"] == "tasks")
    print("task fields:", [(f["id"], f["type"]) for f in tasks["fields"]])

    # enable FreeRTOS through the normal middleware path
    r = call("mode_set", project_id=pid, peripheral="FREERTOS", mode="CMSIS_V2")
    print("mode_set FREERTOS:", r.get("status") or r.get("__error__", "")[:120])

    st = call("rtos_status", project_id=pid)
    print("status:", {k: st[k] for k in ("prefix", "mode", "objects",
                                        "rtos_row_present")})

    r = call("rtos_objects", project_id=pid)
    print("objects:", r.get("count"), [o.get("values", {}).get("name")
                                       for o in r.get("objects", [])][:6])

    r = call("rtos_object_write", project_id=pid, op="add", object_type="tasks",
             fields={"name": "worker", "priority": "osPriorityNormal",
                     "stackSize": "256", "entry": "StartWorker"})
    print("add task:", {k: r.get(k) for k in ("op", "key", "reload")}
          if "__error__" not in r else r)

    r = call("rtos_object_write", project_id=pid, op="add", object_type="queues",
             fields={"name": "cmdQueue", "itemNumber": "8"})
    print("add queue:", {k: r.get(k) for k in ("op", "key", "reload")}
          if "__error__" not in r else r)

    r = call("rtos_object_write", project_id=pid, op="update", object_type="tasks",
             index=1, fields={"stackSize": "512"})
    print("update task:", {k: r.get(k) for k in ("op", "key", "value")}
          if "__error__" not in r else r)

    r = call("rtos_config", project_id=pid,
             values={"configUSE_TIMERS": 1, "configTOTAL_HEAP_SIZE": 4096})
    print("config:", r.get("applied") or r)

    objs = call("rtos_objects", project_id=pid)
    for o in objs["objects"]:
        print("   ", o["key"], "->", o.get("values"))

    r = call("rtos_object_write", project_id=pid, op="delete", object_type="queues",
             index=1)
    print("delete queue:", {k: r.get(k) for k in ("deleted", "reload")}
          if "__error__" not in r else r)

    # duplicate-name protection
    r = call("rtos_object_write", project_id=pid, op="add", object_type="tasks",
             fields={"name": "worker"})
    print("duplicate name rejected:", "__error__" in r)

    r = call("rtos_objects", project_id=pid)
    print("final objects:", [(o["key"], o.get("values", {}).get("name"))
                             for o in r["objects"]])
    proc.stdin.close()
    proc.terminate()
    return 0


if __name__ == "__main__":
    sys.exit(main())
