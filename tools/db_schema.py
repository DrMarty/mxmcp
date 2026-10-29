"""Exhaustive schema extraction from the CubeMX databases under db/.

For every XML family we report: root tag+attributes, element frequencies,
attribute frequency per element, and observed value domains. This documents the
complete data model the GUI/CLI read (MCU, IP modes, IP configs, clock trees,
memory, boards, power, LPBAM, DDR, RIF, CAD, mcufinder, updater).
"""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX\db")
OUT = Path(__file__).resolve().parent.parent / "analysis"


def tag(name: str) -> str:
    return name.split("}")[-1]


def study(paths: list[Path], sample: int | None = None) -> dict:
    paths = [x for x in paths if x.is_file()]
    roots: Counter = Counter()
    root_attrs: Counter = Counter()
    elems: Counter = Counter()
    attrs: dict[str, Counter] = defaultdict(Counter)
    domains: dict[str, dict[str, set]] = defaultdict(lambda: defaultdict(set))
    kinds: dict[str, Counter] = defaultdict(Counter)
    files = paths[:sample] if sample else paths
    errors = 0
    for p in files:
        try:
            tree = ET.parse(p)
        except ET.ParseError:
            errors += 1
            continue
        r = tree.getroot()
        rt = tag(r.tag)
        roots[rt] += 1
        for k, v in r.attrib.items():
            root_attrs[f"{rt}@{k}"] += 1
            if v.isdigit() or len(v) < 24:
                domains[rt][k].add(v)
        for el in r.iter():
            t = tag(el.tag)
            elems[t] += 1
            for k, v in el.attrib.items():
                attrs[t][k] += 1
                if len(v) <= 40 and not v.startswith("0x"):
                    domains[t][k].add(v)
            if (el.text or "").strip():
                kinds[t]["text"] += 1
            else:
                kinds[t]["child-only"] += 1
    return {
        "files_scanned": len(files), "files_total": len(paths), "parse_errors": errors,
        "roots": dict(roots),
        "root_attributes": dict(root_attrs),
        "elements": dict(elems.most_common(200)),
        "attributes": {k: dict(v.most_common(30)) for k, v in attrs.items()},
        "value_domains": {k: {a: sorted(vs)[:40] for a, vs in list(d.items())[:25]}
                          for k, d in domains.items()},
        "content_kinds": {k: dict(v) for k, v in kinds.items()},
    }


GROUPS: list[tuple[str, list[Path], int | None]] = [
    ("mcu", sorted((ROOT / "mcu").glob("*.xml")), 40),
    ("mcu_ip_modes", sorted((ROOT / "mcu" / "IP").glob("*.xml")), 30),
    ("mcu_configs", sorted((ROOT / "mcu" / "config").glob("*.xml")), 30),
    ("mcu_memory", sorted((ROOT / "mcu" / "memory").glob("*.xml")), 20),
    ("mcu_packs_vpdsc", sorted((ROOT / "mcu" / "packs").glob("*.vpdsc")), 10),
    ("families", sorted((ROOT / "mcu").glob("families.xml")), None),
    ("rules", sorted((ROOT / "mcu").glob("rules.xml")), None),
    ("compatibility", sorted((ROOT / "mcu").glob("compatibility.xml")), None),
    ("boardmanager_pdsc", sorted((ROOT / "plugins" / "boardmanager").glob("*.pdsc")), None),
    ("boardmanager_bsp", sorted((ROOT / "plugins" / "boardmanager" / "bsp").glob("*.xml"))
     if (ROOT / "plugins" / "boardmanager" / "bsp").is_dir() else [], None),
    ("updater", sorted((ROOT / "plugins" / "updater").rglob("*.xml")), None),
    ("power", sorted((ROOT / "plugins" / "power").rglob("*.xml")), 20),
    ("lpbam", sorted((ROOT / "plugins" / "lpbam").rglob("*.xml")), None),
    ("clock_plugin", sorted((ROOT / "plugins" / "clock").rglob("*.xml")), None),
    ("mcufinder", sorted((ROOT / "plugins" / "mcufinder").rglob("*.xml")), 20),
    ("pinoutconfig", sorted((ROOT / "plugins" / "pinoutconfig").rglob("*.xml")), 20),
    ("projectmanager", sorted((ROOT / "plugins" / "projectmanager").rglob("*.xml")), 20),
    ("thirdparty", sorted((ROOT / "plugins" / "thirdparty").rglob("*.xml")), 20),
    ("ipmanager", sorted((ROOT / "plugins" / "ipmanager").rglob("*.xml")), 20),
    ("contextual", sorted((ROOT / "contextual").rglob("*.xml"))
     if (ROOT / "contextual").is_dir() else [], 20),
    ("templates_dirs", sorted(x for x in (ROOT / "templates").glob("*") if x.is_file()), None),
    ("all_xml_files", sorted(ROOT.rglob("*.xml")), None),
]


def main() -> int:
    OUT.mkdir(exist_ok=True)
    report: dict[str, dict] = {}
    for name, paths, sample in GROUPS:
        if not paths:
            report[name] = {"files_total": 0}
            continue
        report[name] = study(paths, sample)
        print(f"{name:20s} files={report[name]['files_total']:6d} "
              f"roots={list(report[name]['roots'])[:3]}", flush=True)
    (OUT / "db_schema.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    # directory census (all file types, not only xml)
    census: dict[str, dict[str, int]] = {}
    for p in ROOT.rglob("*"):
        if p.is_file():
            rel = str(p.parent.relative_to(ROOT)).replace("\\", "/")
            ext = p.suffix.lower() or "(none)"
            row = census.setdefault(rel, {})
            row[ext] = row.get(ext, 0) + 1
    (OUT / "db_census.json").write_text(json.dumps(census, indent=1), encoding="utf-8")
    print(f"{len(census)} db directories -> analysis/db_census.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
