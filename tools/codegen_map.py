"""Code-generation chain: who generates what, from which template.

Static evidence collected from the rebuilt jar + shipped data:
  * every class implementing `generateCode(...)` (the plugin IP contract)
  * every `.ftl` literal referenced from Java (template -> owner mapping)
  * the template directory census per toolchain plugin
  * ProjectManager task opcodes
Output: analysis/codegen_map.json.
"""
from __future__ import annotations

import collections
import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX")
HERE = Path(__file__).resolve().parent.parent
JAR = HERE / "_extract" / "cubemx_full.jar"
OUT = HERE / "analysis"

FTL = re.compile(rb"[\w./\\-]{2,120}\.ftl")
GEN_METHOD = "generateCode(java.lang.String, com.st.microxplorer.plugin.IProgressBarMonitor)"
KEEP = re.compile(r"[\x20-\x7e]{4,140}")


def cp_strings(data: bytes) -> list[str]:
    if data[:4] != b"\xca\xfe\xba\xbe":
        return []
    count = int.from_bytes(data[8:10], "big")
    pos = 10
    out: list[str] = []
    i = 1
    while i < count:
        tag = data[pos]
        pos += 1
        if tag == 1:
            ln = int.from_bytes(data[pos:pos + 2], "big")
            pos += 2
            raw = data[pos:pos + ln]
            pos += ln
            try:
                out.append(raw.decode("utf-8"))
            except UnicodeDecodeError:
                out.append(raw.decode("latin-1"))
        elif tag in (7, 8, 16, 19, 20):
            pos += 2
        elif tag == 15:
            pos += 3
        elif tag in (3, 4, 9, 10, 11, 12, 17, 18):
            pos += 4
        elif tag in (5, 6):
            pos += 8
            i += 1
        else:
            break
        i += 1
    return out


def scan_jar(jar: Path, label: str, into: dict) -> None:
    z = zipfile.ZipFile(jar)
    for n in z.namelist():
        if not n.endswith(".class"):
            continue
        strings = cp_strings(z.read(n))
        cls = n[:-6].replace("/", ".")
        hits = sorted({s for s in strings if s.endswith(".ftl")})
        if hits:
            into.setdefault(label, {})[cls] = hits
        if any(GEN_METHOD.split("(")[0] in s for s in strings):
            pass


def main() -> int:
    OUT.mkdir(exist_ok=True)
    tpl_refs: dict[str, dict[str, list[str]]] = {}
    scan_jar(JAR, "app", tpl_refs)
    for jar in sorted((ROOT / "plugins").glob("*.jar")) + \
            sorted((ROOT / "plugins" / "ip").glob("*.jar")):
        scan_jar(jar, jar.name, tpl_refs)

    api = json.loads((OUT / "api_index.json").read_text(encoding="utf-8"))
    generators = {k: v["methods"] for k, v in api.items()
                  if any(m.startswith("java.util.HashMap generateCode(") or
                         " generateCode(" in m for m in v["methods"])}

    shipped = collections.defaultdict(list)
    for p in ROOT.rglob("*.ftl"):
        rel = str(p.relative_to(ROOT)).replace("\\", "/")
        shipped[rel.split("/")[2] if rel.startswith("db/plugins/") else
                rel.split("/")[1]].append(rel)

    report = {
        "template_references_by_class": tpl_refs,
        "classes_implementing_generateCode": sorted(generators),
        "generateCode_signature":
            "HashMap<String, HashMap<String,String>> generateCode(String, IProgressBarMonitor)",
        "template_files_by_location": {k: sorted(v) for k, v in sorted(shipped.items())},
        "template_total": sum(len(v) for v in shipped.values()),
    }
    (OUT / "codegen_map.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    n_refs = sum(len(v) for v in tpl_refs.values())
    print(f"classes referencing templates: {n_refs}; "
          f"generateCode implementors: {len(generators)}; "
          f"templates: {report['template_total']}")
    for loc, lst in sorted(report["template_files_by_location"].items()):
        print(f"  {loc:26s} {len(lst):5d}")
    print("generateCode implementors sample:", list(generators)[:10])
    return 0


if __name__ == "__main__":
    sys.exit(main())
