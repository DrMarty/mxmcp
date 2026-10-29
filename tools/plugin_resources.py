"""Where does each plugin keep its data? (db dir vs inside the jar)

`db/plugins/{lpbam,ddr,rif,memorymap}` do not exist, so those subsystems ship
their models inside the plugin jars. This prints the resource inventory of each
plugin jar (non-class files) so the data contract is discoverable.
"""
from __future__ import annotations

import json
import sys
import zipfile
from collections import Counter
from pathlib import Path

ROOT = Path(r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX\plugins")
OUT = Path(__file__).resolve().parent.parent / "analysis" / "plugin_resources.json"
WANT = ["lpbam", "ddr", "rif", "memorymap", "power", "clock", "pinoutconfig",
        "pinoutandconfiguration", "cadmodel", "projectmanager", "thirdparty",
        "updater", "ipmanager", "filemanager", "analytics", "userauth",
        "tutovideos", "tools"]


def main() -> int:
    report: dict[str, dict] = {}
    for name in WANT:
        jar = ROOT / f"{name}.jar"
        if not jar.exists():
            report[name] = {"exists": False}
            continue
        z = zipfile.ZipFile(jar)
        names = z.namelist()
        res = [n for n in names if not n.endswith("/") and not n.endswith(".class")]
        kinds = Counter(Path(n).suffix.lower() or "(none)" for n in res)
        xml = [n for n in res if n.endswith((".xml", ".xsd"))]
        jsonf = [n for n in res if n.endswith(".json")]
        ftl = [n for n in res if n.endswith(".ftl")]
        report[name] = {
            "exists": True, "entries": len(names),
            "classes": sum(1 for n in names if n.endswith(".class")),
            "resource_kinds": dict(kinds.most_common(10)),
            "xml": sorted(xml)[:25], "json": sorted(jsonf)[:15],
            "ftl": sorted(ftl)[:15],
            "resource_count": len(res),
        }
        print(f"{name:24s} res={len(res):5d} xml={len(xml):4d} json={len(jsonf):3d} "
              f"ftl={len(ftl):4d}  {sorted(xml)[:2]}")
    OUT.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print("->", OUT.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
