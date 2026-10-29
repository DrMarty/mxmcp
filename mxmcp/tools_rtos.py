"""RTOS user-object editing (the CubeMX "FreeRTOS / RTOS" tab).

CubeMX stores free-form RTOS objects in the .ioc as
``<PREFIX>.<ListSlug><nn>=f1,f2,f3,...`` in the field order declared by
``rtos_apis.xml`` (shipped inside the app jar, extracted to
``analysis/rtos_model.json``), plus ``<PREFIX>.IPParameters`` listing the keys and
``<PREFIX>.config*`` scalars. The schema for CMSIS RTOS v1/v2 is:

  Tasks01, Queues01, Timers01, BinarySemaphores01, CountingSemaphores01,
  Mutexes01, RecursiveMutexes01, Events01   (list name + 2-digit index)

Enabled/disabled fields are decided by JavaScript expressions in that XML
(`allocationType === 'Static'`), evaluated against ``RtosBindings`` over the IP —
so this module mirrors the same rules in Python and validates field values and
unique-name constraints before writing, then reloads the project through the
engine and saves with CubeMX itself (the .ioc stays authoritative).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import schema as S
from .rpc import ToolError
from .store import ProjectManager

DATA = Path(__file__).resolve().parent / "data"
_MODEL: dict | None = None
LIST_KEY = re.compile(r"^(?P<list>[A-Za-z][A-Za-z0-9]*?)(?P<idx>\d{2})$")


def model() -> dict:
    """The RTOS object schema (analysed from rtos_apis.xml)."""
    global _MODEL
    if _MODEL is None:
        path = DATA / "rtos_model.json"
        if not path.exists():
            raise ToolError(
                "the RTOS schema snapshot is missing "
                f"({path.name}); regenerate it with tools/rtos_model.py")
        _MODEL = json.loads(path.read_text(encoding="utf-8"))
    return _MODEL


def api_by_label(label: str) -> dict:
    for api in model()["apis"]:
        if (api["label"] or "").lower() == label.lower() or \
                (api["class"] or "").lower() == label.lower():
            return api
    raise ToolError(f"unknown RTOS API {label!r}; available: "
                    f"{[a['label'] for a in model()['apis']]}")


def objects_of(api: dict) -> dict:
    """`{data id: {label, list, fields...}}` for one API."""
    out = {}
    for grp in api["groups"]:
        for data in grp["data"]:
            key = data["id"]
            out.setdefault(key, []).append({"group": grp["label"], **data})
    return out


def field_ids(data: dict) -> list[str]:
    return [f["id"] for f in data["fields"]]


def enabled_for(field: dict, values: dict) -> bool:
    """Evaluate the (single) `<enabled condition>` the shipped XML uses.

    Every condition in rtos_apis.xml is a single `field === 'Value'` test, so the
    check is exact without a JS runtime; anything else is treated as enabled and
    reported by the caller.
    """
    conds = field.get("enabled") or []
    for c in conds:
        expr = (c.get("condition") or "").strip().rstrip(";")
        m = re.match(r"^(\w+)\s*===\s*'([^']*)'$", expr)
        if m:
            if str(values.get(m.group(1), "")) != m.group(2):
                return False
            continue
        return True
    return True


def slug(list_name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", list_name)


def find_prefix(ioc) -> str:
    """The .ioc prefix of the active RTOS (`FREERTOS`, `XCB_FRT`...)."""
    for key in ioc.entries:
        head = key.split(".", 1)[0]
        if head.upper().startswith(("FREERTOS", "XCUBEFREERTOS", "XCB_FRT",
                                   "THREADX", "AZRTOS", "RTOS")):
            return head
    return "FREERTOS"


def parse_object(text: str, data: dict) -> dict:
    """Split a stored comma list into {field id: value} using the XML order."""
    parts = [p.strip() for p in (text or "").split(",")]
    ids = field_ids(data)
    out = {}
    for i, fid in enumerate(ids):
        out[fid] = parts[i] if i < len(parts) else ""
    if len(parts) > len(ids):
        out["__extra__"] = ",".join(parts[len(ids):])
    return out


def register(server, pm: ProjectManager) -> None:
    def rtos_schema(args: dict):
        m = model()
        apis = []
        for api in m["apis"]:
            objs = []
            for grp in api["groups"]:
                for data in grp["data"]:
                    objs.append({
                        "group": grp["label"], "object": data["label"],
                        "id": data["id"], "list": data["list"],
                        "fields": [{"id": f["id"], "label": f["label"],
                                    "type": f["type"], "default": f["default"],
                                    "unique": f["unique"],
                                    "values": [v["value"] for v in f["values"]],
                                    "enabled_condition": [c["condition"] for c in
                                                          f["enabled"]]}
                                   for f in data["fields"]]})
            apis.append({"api": api["label"], "class": api["class"],
                         "semaphore": api.get("semaphore"), "objects": objs})
        return {"source": m["source"], "storage": m["storage"],
                "js_bindings": m["js_bindings"], "apis": apis}

    server.tool(
        "rtos_schema",
        "The RTOS user-object schema CubeMX ships (tasks/queues/timers/semaphores/"
        "mutexes/events per CMSIS RTOS v1 & v2), including every field, its "
        "default, allowed values, the JS enabled-condition, and how the objects "
        "are stored in the .ioc.",
        S.obj({}), rtos_schema)

    def _state(p) -> dict:
        # CubeMX writes the whole RTOS table (objects + config defaults) only to
        # the extended file, so the coherent view merges project_ext.ioc.
        ioc = p.ioc().merged(p.dir / "project_ext.ioc")
        prefix = find_prefix(ioc)
        api = None
        for cand in ("CMSIS RTOS2", "CMSIS RTOS1", "Default"):
            try:
                api = api_by_label(cand)
            except ToolError:
                continue
            break
        return {"ioc": ioc, "prefix": prefix, "api": api}

    def rtos_status(args: dict):
        p = pm.get(args.get("project_id"))
        st = _state(p)
        ioc, prefix = st["ioc"], st["prefix"]
        registered = ioc.get(f"{prefix}.IPParameters") or ""
        keys = [k.strip() for k in registered.split(",") if k.strip()]
        # middleware IPs are registered by name in Mcu.IP0..N (no .Mode key)
        mode = ""
        for k in ioc.keys("Mcu.IP"):
            if ioc.get(k) == prefix:
                mode = prefix
                break
        if not mode:
            mode = ioc.get(f"{prefix}.Mode") or ioc.get(f"{prefix}.VirtualMode") or ""
        objs: dict[str, int] = {}
        for key in ioc.entries:
            if not key.startswith(prefix + "."):
                continue
            name = key.split(".", 1)[1]
            m = LIST_KEY.match(name)
            if m:
                objs[m.group("list")] = objs.get(m.group("list"), 0) + 1
        return {"project_id": p.pid, "prefix": prefix, "mode": mode,
                "ip_parameters": keys, "objects": objs,
                "config": {k.split(".", 1)[1]: v for k, v in ioc.entries.items()
                           if k.startswith(prefix + ".config")},
                "rtos_row_present": bool(mode or registered),
                "note": ("RTOS objects live in the .ioc; the engine reads them on "
                         "load, so edits made here are applied by reloading and "
                         "saving through CubeMX")}

    server.tool(
        "rtos_status",
        "Read the project's RTOS state: active mode, the .ioc prefix, every stored "
        "object per type, the FreeRTOS config scalars, and whether the RTOS row is "
        "present.",
        S.obj({"project_id": S.s("Project id (defaults to the last used)")}),
        rtos_status)

    def rtos_objects(args: dict):
        p = pm.get(args.get("project_id"))
        st = _state(p)
        ioc, prefix = st["ioc"], st["prefix"]
        api = api_by_label(args["api"]) if args.get("api") else st["api"]
        types = objects_of(api)
        wanted = args.get("object_type")
        if wanted and wanted not in types:
            raise ToolError(f"unknown object type {wanted!r}; "
                            f"available: {sorted(types)}")
        rows = []
        for key, value in ioc.entries.items():
            if not key.startswith(prefix + "."):
                continue
            name = key.split(".", 1)[1]
            m = LIST_KEY.match(name)
            if not m:
                continue
            list_name = m.group("list")
            data = next((d for d in types.get(wanted or "", []) if d  # noqa: SIM401
                         and slug(d["list"]) == list_name), None)
            if data is None:
                for t in types.values():
                    for d in t:
                        if slug(d["list"]) == list_name:
                            data = d
                            break
            if data is None:
                rows.append({"key": key, "list": list_name,
                             "index": m.group("idx"), "raw": value,
                             "field_order": None})
                continue
            if wanted and slug(data["list"]) != list_name:
                continue
            rows.append({"key": key, "type": data["label"],
                         "list": list_name, "index": m.group("idx"),
                         "values": parse_object(value, data),
                         "field_order": field_ids(data)})
        rows.sort(key=lambda r: (str(r.get("list")), str(r.get("index"))))
        return {"project_id": p.pid, "prefix": prefix, "api": api["label"],
                "count": len(rows), "objects": rows}

    server.tool(
        "rtos_objects",
        "List the RTOS objects stored in the project with their fields decoded "
        "according to the shipped schema (field order from rtos_apis.xml).",
        S.obj({"project_id": S.s("Project id"),
               "object_type": S.s("Data id, e.g. tasks / queues / timers "
                                  "(default: all)"),
               "api": S.s("RTOS API label, e.g. 'CMSIS RTOS2'")},
              []), rtos_objects)

    def rtos_object_write(args: dict):
        p = pm.get(args.get("project_id"))
        st = _state(p)
        ioc, prefix = st["ioc"], st["prefix"]
        api = api_by_label(args["api"]) if args.get("api") else st["api"]
        types = objects_of(api)
        otype = args["object_type"]
        if otype not in types:
            raise ToolError(f"unknown object type {otype!r}; available: "
                            f"{sorted(types)}")
        data = types[otype][0]
        ids = field_ids(data)
        op = args["op"]

        # existing objects of this type
        existing: dict[str, tuple[str, dict]] = {}
        for key, value in ioc.entries.items():
            if not key.startswith(prefix + "."):
                continue
            m = LIST_KEY.match(key.split(".", 1)[1])
            if m and slug(data["list"]) == m.group("list"):
                existing[m.group("idx")] = (key, parse_object(value, data))

        if op == "add":
            values = {f["id"]: str(f["default"] or "") for f in data["fields"]}
            for k, v in (args.get("fields") or {}).items():
                if k not in ids:
                    raise ToolError(f"unknown field {k!r} for {otype}; "
                                    f"fields: {ids}")
                values[k] = str(v)
            values.update({k: str(v) for k, v in (args.get("fields") or {}).items()})
            # unique-name constraint enforced by the GUI
            uniq = [f["id"] for f in data["fields"] if f["unique"]]
            for uid in uniq:
                for key, vals in existing.values():
                    if vals.get(uid) and vals.get(uid) == values.get(uid):
                        raise ToolError(
                            f"{uid}={values[uid]!r} is already used by {key}; "
                            f"names must be unique")
            idx = 1
            while f"{idx:02d}" in existing:
                idx += 1
            key = f"{prefix}.{data['list']}{idx:02d}"
            joined = ",".join(values.get(i, "") for i in ids)
        elif op == "update":
            if not args.get("index"):
                raise ToolError("update needs index=")
            key = f"{prefix}.{data['list']}{int(args['index']):02d}"
            if key not in ioc.entries:
                raise ToolError(f"{key} does not exist")
            values = parse_object(ioc.get(key) or "", data)
            for k, v in (args.get("fields") or {}).items():
                if k not in ids:
                    raise ToolError(f"unknown field {k!r}; fields: {ids}")
                values[k] = str(v)
            joined = ",".join(values.get(i, "") for i in ids)
        elif op == "delete":
            if not args.get("index"):
                raise ToolError("delete needs index=")
            key = f"{prefix}.{data['list']}{int(args['index']):02d}"
            if key not in ioc.entries:
                raise ToolError(f"{key} does not exist")
            ioc.drop_ip_param(prefix, key.split(".", 1)[1]) \
                if hasattr(ioc, "drop_ip_param") else ioc.entries.pop(key, None)
            ioc.save(p.ioc_path)
            reload_res = pm.run(p, f'config load "{p.ioc_path}"', timeout=300)
            return {"project_id": p.pid, "deleted": key,
                    "reload": reload_res["status"]}
        else:  # pragma: no cover
            raise ToolError(f"unknown op {op!r}")

        if op == "add":
            # keep the % field used by the GUI for ordering
            ioc.set(f"{prefix}.{data['list']}{int(key[-2:]):02d}", joined)
        else:
            ioc.set(key, joined)
        names = [k.strip() for k in
                 (ioc.get(f"{prefix}.IPParameters") or "").split(",") if k.strip()]
        short = key.split(".", 1)[1]
        if short not in names:
            names.append(short)
            ioc.set(f"{prefix}.IPParameters", ",".join(names))
        ioc.save(p.ioc_path)
        reload_res = pm.run(p, f'config load "{p.ioc_path}"', timeout=300)
        if reload_res["status"] != "OK":
            raise ToolError(f"CubeMX rejected the edited project: "
                            f"{reload_res['output'][:300]}")
        pm.save(p)
        return {"project_id": p.pid, "op": op, "key": key, "value": joined,
                "fields": dict(zip(ids, joined.split(","))),
                "reload": reload_res["status"]}

    server.tool(
        "rtos_object_write",
        "Add / update / delete an RTOS object (task, queue, timer, semaphore, "
        "mutex, event) with schema validation and the GUI's unique-name rule, then "
        "let CubeMX reload and re-save the project so the .ioc is canonical.",
        S.obj({"project_id": S.s("Project id"),
               "op": S.enum(["add", "update", "delete"], "Operation"),
               "object_type": S.s("Data id, e.g. tasks / queues / timers / "
                                  "binarySems / mutexes"),
               "index": S.i("Object index for update/delete"),
               "fields": S.anyobj("Field overrides, keyed by field id (name, "
                                  "priority, stackSize, entry, allocationType…)"),
               "api": S.s("RTOS API label (default: detected)")},
              ["op", "object_type"]), rtos_object_write)

    def rtos_config(args: dict):
        p = pm.get(args.get("project_id"))
        st = _state(p)
        ioc, prefix = st["ioc"], st["prefix"]
        if args.get("values"):
            names = [k.strip() for k in
                     (ioc.get(f"{prefix}.IPParameters") or "").split(",") if k.strip()]
            for k, v in args["values"].items():
                if not k.startswith("config"):
                    raise ToolError("FreeRTOS options start with 'config' "
                                    "(configUSE_TIMERS, configTOTAL_HEAP_SIZE…)")
                ioc.set(f"{prefix}.{k}", str(v))
                if k not in names:
                    names.append(k)
            ioc.set(f"{prefix}.IPParameters", ",".join(names))
            ioc.save(p.ioc_path)
            res = pm.run(p, f'config load "{p.ioc_path}"', timeout=300)
            if res["status"] != "OK":
                raise ToolError(f"CubeMX rejected {args['values']}: "
                                f"{res['output'][:300]}")
            pm.save(p)
            return {"project_id": p.pid, "applied": args["values"],
                    "reload": res["status"]}
        return {"project_id": p.pid, "prefix": prefix,
                "config": {k.split(".", 1)[1]: v for k, v in ioc.entries.items()
                           if k.startswith(prefix + ".config")}}

    server.tool(
        "rtos_config",
        "Read or set FreeRTOS configuration scalars (configUSE_TIMERS, "
        "configTOTAL_HEAP_SIZE, configMAX_PRIORITIES…), registering each key in "
        "IPParameters exactly like the GUI does.",
        S.obj({"project_id": S.s("Project id"),
               "values": S.anyobj("config* values to apply, e.g. "
                                  "{\"configUSE_TIMERS\": 1}")}),
        rtos_config)
