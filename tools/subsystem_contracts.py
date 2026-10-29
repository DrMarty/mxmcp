"""Close the remaining reverse-engineering gaps.

Covers the data/subsystems that the earlier passes only counted:

  db/plugins/power    battery/consumption models + RF/SubGHz scenarios
  db/plugins/lpbam    low-power DMA sequencing descriptions
  db/plugins/ddr      DDR controller training/geometry data
  db/plugins/rif      RIF (resource isolation) rules
  db/plugins/memorymap memory-map tool data
  db/plugins/clock    clock tree definitions (per family)
  utilities           STM32PackCreator (CMSIS-Pack builder) surface
  olddb               legacy database archive
  third_parties_plugins  embedded p2 repository inventory

For each: the XML/JSON contract (root, elements, attributes, domain values),
class counts and entry points, so nothing in the product is undocumented.
"""
from __future__ import annotations

import bz2
import json
import re
import sys
import tarfile
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX")
OUT = Path(__file__).resolve().parent.parent / "analysis" / "subsystem_contracts.json"


def _local(t: str) -> str:
    return t.split("}")[-1]


def study_xml(paths: list[Path], sample: int = 60) -> dict:
    roots: Counter = Counter()
    elems: Counter = Counter()
    attrs: dict[str, Counter] = defaultdict(Counter)
    domains: dict[str, dict[str, set]] = defaultdict(lambda: defaultdict(set))
    errors = 0
    for p in paths[:sample]:
        try:
            tree = ET.parse(p)
        except (ET.ParseError, OSError):
            errors += 1
            continue
        r = tree.getroot()
        roots[_local(r.tag)] += 1
        for el in r.iter():
            t = _local(el.tag)
            elems[t] += 1
            for k, v in el.attrib.items():
                attrs[t][k] += 1
                if len(v) <= 40:
                    domains[t][k].add(v)
    return {"files": len(paths), "sampled": min(len(paths), sample),
            "parse_errors": errors, "roots": dict(roots),
            "elements": dict(elems.most_common(40)),
            "attributes": {k: dict(v.most_common(12)) for k, v in
                           list(attrs.items())[:25]},
            "domains": {k: {a: sorted(vs)[:12] for a, vs in list(d.items())[:10]}
                        for k, d in list(domains.items())[:15]}}


def study_json(paths: list[Path], sample: int = 30) -> dict:
    keys: Counter = Counter()
    shapes: dict[str, Counter] = defaultdict(Counter)
    errors = 0
    for p in paths[:sample]:
        try:
            data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
        except (json.JSONDecodeError, OSError):
            errors += 1
            continue

        def walk(node, prefix="", depth=0):
            if depth > 3:
                return
            if isinstance(node, dict):
                for k, v in node.items():
                    keys[f"{prefix}{k}"] += 1
                    shapes[f"{prefix}{k}"][type(v).__name__] += 1
                    walk(v, f"{prefix}{k}.", depth + 1)
            elif isinstance(node, list) and node:
                walk(node[0], f"{prefix}[].", depth + 1)

        walk(data)
    return {"files": len(paths), "sampled": min(len(paths), sample),
            "parse_errors": errors, "keys": dict(keys.most_common(60)),
            "shapes": {k: dict(v) for k, v in list(shapes.items())[:40]}}


def jar_classes(path: Path) -> dict:
    try:
        z = zipfile.ZipFile(path)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
    names = z.namelist()
    classes = [n for n in names if n.endswith(".class")]
    pkgs: Counter = Counter()
    for c in classes:
        pkgs["/".join(c.split("/")[:3])] += 1
    # entry points / UI panels / CLI hints
    hints = Counter()
    for c in classes:
        for token, label in (("Main", "main"), ("Panel", "panel"),
                            ("Dialog", "dialog"), ("Wizard", "wizard"),
                            ("Pack", "pack"), ("Pdsc", "pdsc"),
                            ("Command", "command")):
            if token in c:
                hints[label] += 1
    return {"entries": len(names), "classes": len(classes),
            "top_packages": dict(pkgs.most_common(12)),
            "hint_counts": dict(hints)}


def olddb() -> dict:
    base = ROOT / "olddb"
    if not base.exists():
        return {"exists": False}
    out = {"exists": True, "files": []}
    for p in base.rglob("*"):
        if not p.is_file():
            continue
        rec = {"name": p.name, "bytes": p.stat().st_size}
        if p.suffix == ".bz2":
            try:
                with bz2.open(p, "rb") as fh:
                    head = fh.read(4096)
                rec["magic"] = head[:8].hex()
                rec["is_tar"] = head[257:262] == b"ustar"
                rec["first_names"] = [m.group().decode("latin-1")
                                      for m in re.finditer(rb"[\w./-]{6,60}", head)][:8]
            except OSError as exc:
                rec["error"] = str(exc)
        out["files"].append(rec)
    return out


def third_parties() -> dict:
    base = ROOT / "third_parties_plugins"
    if not base.exists():
        return {"exists": False}
    jars, cls = [], 0
    for p in base.rglob("*.jar"):
        jars.append({"name": p.name, "bytes": p.stat().st_size})
    for p in base.rglob("*.class"):
        cls += 1
    plugins = [p.name for p in (base / "binaries" / "STM32CubeIDE-MX-services" /
                                "revA" / "pool" / "plugins").glob("*")
               if p.is_dir()] if base.exists() else []
    return {"exists": True, "jars": sorted(jars, key=lambda r: -r["bytes"])[:12],
            "class_files": cls, "p2_bundles": len(plugins), "bundles": plugins[:8]}


GROUPS: list[tuple[str, Path, str]] = [
    ("power_xml", ROOT / "db" / "plugins" / "power", "xml"),
    ("power_json", ROOT / "db" / "plugins" / "power", "json"),
    ("lpbam", ROOT / "db" / "plugins" / "lpbam", "xml"),
    ("ddr", ROOT / "db" / "plugins" / "ddr", "xml"),
    ("rif", ROOT / "db" / "plugins" / "rif", "xml"),
    ("memorymap", ROOT / "db" / "plugins" / "memorymap", "xml"),
    ("clock", ROOT / "db" / "plugins" / "clock", "xml"),
]


def main() -> int:
    report: dict = {}
    for name, base, kind in GROUPS:
        if not base.exists():
            report[name] = {"exists": False}
            print(f"{name:14s} (absent)")
            continue
        files = sorted(base.rglob(f"*.{kind}"))
        rec = study_xml(files) if kind == "xml" else study_json(files)
        rec["exists"] = True
        report[name] = rec
        print(f"{name:14s} files={rec['files']:4d} roots={list(rec.get('roots', {}))[:3]}"
              f" keys={len(rec.get('keys', {}))}")

    report["utilities"] = {
        "class_summary": jar_classes(ROOT / "utilities" / "STM32PackCreator" /
                                     "STM32PackCreator.jar"),
        "files": [{"name": p.name, "bytes": p.stat().st_size}
                  for p in (ROOT / "utilities").rglob("*") if p.is_file()][:20],
    }
    report["uninstaller"] = {
        "class_summary": jar_classes(ROOT / "Uninstaller" / "uninstaller.jar"),
    }
    report["olddb"] = olddb()
    report["third_parties"] = third_parties()

    OUT.write_text(json.dumps(report, indent=1), encoding="utf-8")
    ut = report["utilities"]["class_summary"]
    print(f"STM32PackCreator: {ut.get('classes')} classes, "
          f"hints={ut.get('hint_counts')}")
    print(f"uninstaller: {report['uninstaller']['class_summary'].get('classes')} classes")
    print(f"olddb: {[f['name'] for f in report['olddb'].get('files', [])]}")
    print(f"third_party p2 bundles: {report['third_parties'].get('p2_bundles')}")
    print("->", OUT.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
