"""Document the CubeIDE-MX services backend (the real generator for CubeIDE /
Makefile / CMake projects) and the mxScratch interchange format.

CubeMX writes an *mxScratch* XML (schema mxScratch_v30.xsd) and then invokes the
embedded Eclipse p2 repository `STM32CubeIDE-MX-services` head-less; each
`--service <name>` performs one step (projectSetup, buildSetup, lnkSetup,
dtSetup, startupSetup, threadSafeSetup, cleanup, ...).

Outputs:
  analysis/cubeide_services.json   services, options, errors, plugin versions
  analysis/mxscratch_schema.json   element/attribute tree of the scratch format
"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

ROOT = Path(r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX")
POOLS = ROOT / "third_parties_plugins" / "binaries" / "STM32CubeIDE-MX-services"
OUT = Path(__file__).resolve().parent.parent / "analysis"

PROP_KEY = re.compile(r"^(\w+?)_(OptionKeyPlain|OptionKeyShort|OptionUsage|Description|Error)"
                      r"_?(\w*)_(\w+)_Text\s*=\s*(.*)$")


def load_props(path: Path) -> dict:
    rows = defaultdict(dict)
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("#") or "=" not in line or line.startswith(" "):
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().replace("\\'", "'")
        m = re.match(r"^([A-Za-z0-9]+)_(\w+)(?:_(\w+))?_Text$", key)
        if not m:
            rows["raw"][key] = val
            continue
        svc, kind, rest = m.groups()
        rows[svc][f"{kind}:{rest or ''}"] = val
    return {k: dict(v) for k, v in rows.items()}


def schema_tree(xsd: Path) -> dict:
    """Flatten an XSD into element/attribute names with their types."""
    ns = "{http://www.w3.org/2001/XMLSchema}"
    root = ET.parse(xsd).getroot()
    local: dict[str, dict] = {}
    for tg in root.findall(ns + "complexType"):
        name = tg.get("name", "")
        els = []
        for el in tg.iter(ns + "element"):
            if el.get("name"):
                els.append({"name": el.get("name"), "type": el.get("type", ""),
                            "min": el.get("minOccurs", "1"),
                            "max": el.get("maxOccurs", "1")})
        attrs = [{"name": a.get("name"), "type": a.get("type", ""),
                  "use": a.get("use", "optional")}
                 for a in tg.iter(ns + "attribute") if a.get("name")]
        local[name] = {"elements": els, "attributes": attrs}
    top = []
    for el in root.findall(ns + "element"):
        top.append({"name": el.get("name"), "type": el.get("type", "")})
    simple = {}
    for st in root.findall(ns + "simpleType"):
        rst = st.find(ns + "restriction")
        vals = [f.get("value") for f in (rst.findall(ns + "enumeration") if rst is not None else [])]
        if vals:
            simple[st.get("name", "")] = vals
    return {"root_elements": top, "complexTypes": local, "enums": simple}


def main() -> int:
    OUT.mkdir(exist_ok=True)
    plugins = {}
    props_all = {}
    for pool in sorted(POOLS.rglob("pool/plugins/*")):
        if not pool.is_dir():
            continue
        name = pool.name
        plugins[name] = sorted(p.name for p in pool.rglob("*.properties"))[:10]
        for p in pool.rglob("UiMessages.properties"):
            props_all[name] = load_props(p)
    xsd = next(iter(POOLS.rglob("mxScratch_v30.xsd")), None)
    scratch = schema_tree(xsd) if xsd else {}
    report = {
        "p2_repository": str(POOLS),
        "plugins": plugins,
        "services": props_all,
        "mxscratch_schema_file": str(xsd) if xsd else None,
        "mxscratch_schema": scratch,
    }
    (OUT / "cubeide_services.json").write_text(json.dumps(report, indent=1),
                                                encoding="utf-8")
    total_services = set()
    for bundle in props_all.values():
        for svc in bundle:
            if svc.endswith("Service"):
                total_services.add(svc)
    print(f"{len(plugins)} p2 plugins, {len(props_all)} message bundles, "
          f"{len(total_services)} service classes")
    if xsd:
        print("mxScratch root elements:", [e["name"] for e in scratch["root_elements"]][:12])
        print("mxScratch types:", list(scratch["complexTypes"])[:20])
    return 0


if __name__ == "__main__":
    sys.exit(main())
