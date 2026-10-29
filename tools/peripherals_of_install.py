"""Document the parts of the install tree that are not the main application.

* `utilities/`        STM32PackCreator (CMSIS-Pack builder) + TrustedPackageCreator
* `Uninstaller/`      IzPack uninstaller (panels, packs)
* `olddb/`            legacy database kept for migration
* `third_parties_plugins/`  the embedded Eclipse p2 repo + MX services jar
* `db/defines`, `db/schema`, `db/key`, `db/extra_templates`

For each area: file census, jar class counts, top-level packages, and any
descriptor (plugin.xml, feature.xml, izpack install.xml) that defines behaviour.
"""
from __future__ import annotations

import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX")
OUT = Path(__file__).resolve().parent.parent / "analysis" / "peripherals_of_install.json"

AREAS = ["utilities", "Uninstaller", "olddb", "third_parties_plugins",
         "db/defines", "db/schema", "db/key", "db/extra_templates", "jre",
         "help", "db/plugins"]


def census(area: str) -> dict:
    base = ROOT / area
    if not base.exists():
        return {"exists": False}
    files = []
    total = 0
    for p in base.rglob("*"):
        if not p.is_file():
            continue
        try:
            size = p.stat().st_size
        except OSError:
            continue
        total += size
        files.append((str(p.relative_to(base)).replace("\\", "/"), size))
    files.sort(key=lambda x: -x[1])
    return {"exists": True, "files": len(files), "bytes": total,
            "largest": files[:12],
            "by_ext": _by_ext(files)}


def _by_ext(files) -> dict:
    out: dict[str, int] = {}
    for name, _ in files:
        ext = Path(name).suffix.lower() or "(none)"
        out[ext] = out.get(ext, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1])[:14])


def jar_summary(path: Path) -> dict:
    try:
        z = zipfile.ZipFile(path)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
    names = z.namelist()
    classes = [n for n in names if n.endswith(".class")]
    pkgs: dict[str, int] = {}
    for c in classes:
        pkg = c.rsplit("/", 1)[0]
        top = "/".join(pkg.split("/")[:3])
        pkgs[top] = pkgs.get(top, 0) + 1
    desc = [n for n in names if n.endswith((".xml", ".properties", ".MF"))
            and ("plugin" in n.lower() or "MANIFEST" in n or "feature" in n.lower())]
    return {"entries": len(names), "classes": len(classes),
            "top_packages": dict(sorted(pkgs.items(), key=lambda kv: -kv[1])[:10]),
            "descriptors": desc[:12]}


def izpack(area: str) -> dict:
    """IzPack install.xml/panels tell us what the installer does."""
    base = ROOT / area
    out: dict[str, str] = {}
    for p in base.rglob("*.xml"):
        if p.name.lower() not in ("install.xml", "auto-install.xml"):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        panels = re.findall(r'<panel[^>]*className="([^"]+)"', text)
        packs = re.findall(r'<pack name="([^"]+)"', text)
        out[p.name] = {"panels": panels[:14], "packs": packs[:10]}
    return out


def main() -> int:
    report: dict = {}
    for area in AREAS:
        info = census(area)
        if area == "utilities" or area == "Uninstaller":
            jars = []
            for p in (ROOT / area).rglob("*.jar"):
                jars.append({"path": str(p.relative_to(ROOT)).replace("\\", "/"),
                             **jar_summary(p)})
            info["jars"] = jars
        if area in ("Uninstaller", "utilities"):
            info["izpack"] = izpack(area)
        report[area] = info
        if info.get("exists"):
            print(f"{area:24s} files={info['files']:6d} "
                  f"{info['bytes']/1e6:8.1f} MB {list(info['by_ext'])[:6]}",
                  flush=True)
        else:
            print(f"{area:24s} (absent)", flush=True)
    OUT.write_text(json.dumps(report, indent=1), encoding="utf-8")
    for area in ("utilities", "Uninstaller"):
        for j in report.get(area, {}).get("jars", []):
            print(f"  jar {j['path']}: {j.get('classes')} classes "
                  f"{list(j.get('top_packages', {}))[:4]}")
    print("-> ", OUT.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
