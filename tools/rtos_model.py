"""Extract the RTOS user-objects model from the shipped rtos_apis.xml.

The CubeMX RTOS tab edits free-form objects (tasks, queues, timers, semaphores,
mutexes, events) whose schema is defined by `rtos_apis.xml` inside the app jar:
`<rtos><api label class group semaphore/>` then
`<group label><data label id list><field label id type default unique><value/>
<enabled condition=JS/></data></group>`.

Objects are persisted in the .ioc as `PREFIX.<List><nn>=v1,v2,…` (field order),
with `PREFIX.IPParameters` listing the keys — which is why CubeMX can round-trip
them. The `<enabled condition>` scripts are evaluated by the GraalJS engine with
`RtosBindings` (parent bindings + the current IP), i.e. real JS in the product.

Outputs analysis/rtos_model.json and docs/rtos_apis.xml (verbatim copy).
"""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
JAR = HERE / "_extract" / "cubemx_full.jar"
MEMBER = "com/st/microxplorer/mcu/rtos/api/rtos_apis.xml"
OUT = HERE / "analysis" / "rtos_model.json"
RAW = HERE / "docs" / "rtos_apis.xml"


def main() -> int:
    z = zipfile.ZipFile(JAR)
    raw = z.read(MEMBER).decode("utf-8", "replace")
    RAW.write_text(raw, encoding="utf-8")
    root = ET.fromstring(raw)
    apis = []
    for rtos in root.findall("rtos"):
        for api in rtos.findall("api"):
            entry = {"label": api.get("label"), "class": api.get("class"),
                     "group": api.get("group"), "semaphore": api.get("semaphore"),
                     "groups": []}
            for grp in rtos.findall("group"):
                g = {"label": grp.get("label"), "data": []}
                for data in grp.findall("data"):
                    d = {"label": data.get("label"), "id": data.get("id"),
                         "list": data.get("list"),
                         "enabled": [{"condition": e.get("condition"),
                                      "diagnostic": e.get("diagnostic")}
                                     for e in data.findall("enabled")],
                         "fields": []}
                    for f in data.findall("field"):
                        fd = {"label": f.get("label"), "id": f.get("id"),
                              "type": f.get("type"), "default": f.get("default"),
                              "unique": f.get("unique") == "true",
                              "values": [{"label": v.get("label"),
                                          "value": (v.text or "").strip()}
                                         for v in f.findall("value")],
                              "enabled": [{"condition": e.get("condition"),
                                           "diagnostic": e.get("diagnostic")}
                                          for e in f.findall("enabled")]}
                        d["fields"].append(fd)
                    g["data"].append(d)
                entry["groups"].append(g)
            apis.append(entry)
    model = {"source": MEMBER, "showHeap": root.get("showHeap"),
             "apis": apis,
             "storage": {
                 "key_pattern": "<PREFIX>.<list-slug><nn>=<field values joined by ','>",
                 "registration": "<PREFIX>.IPParameters=<keys>,configUSE_...,…",
                 "observed_examples": [
                     "FREERTOS.Tasks01=defaultTask,0,128,StartDefaultTask,Default,NULL",
                     "FREERTOS.IPParameters=Tasks01,configUSE_TIMERS,…",
                     "FREERTOS.configTOTAL_HEAP_SIZE=32768"]},
             "js_bindings": "com.st.microxplorer.mcu.rtos.data.RtosBindings "
                            "(javax.script.Bindings over the current IP; GraalJS)"}
    OUT.write_text(json.dumps(model, indent=1), encoding="utf-8")
    for a in apis:
        tot = sum(len(d["fields"]) for g in a["groups"] for d in g["data"])
        print(f"api {a['label']!r} class={a['class']} groups={len(a['groups'])} "
              f"objects={sum(len(g['data']) for g in a['groups'])} fields={tot}")
    print("-> analysis/rtos_model.json, docs/rtos_apis.xml")
    return 0


if __name__ == "__main__":
    sys.exit(main())
