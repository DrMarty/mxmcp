"""Inventory every jar shipped with STM32CubeMX.

Emits analysis/jars.json: for each jar -> size, entry counts, non-class resources
(many plugins ship .xml/.properties descriptors that define the plugin contract),
manifest attributes, and the list of top-level packages.
"""
from __future__ import annotations

import json
import sys
import zipfile
from collections import Counter
from pathlib import Path

ROOT = Path(r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX")
HERE = Path(__file__).resolve().parent.parent
OUT = HERE / "analysis"


def jar_info(path: Path) -> dict:
    info: dict = {"path": str(path.relative_to(ROOT)).replace("\\", "/"),
                  "bytes": path.stat().st_size}
    try:
        z = zipfile.ZipFile(path)
    except Exception as exc:  # noqa: BLE001
        info["error"] = str(exc)
        return info
    names = z.namelist()
    classes = [n for n in names if n.endswith(".class")]
    info["entries"] = len(names)
    info["classes"] = len(classes)
    info["packages"] = sorted({"/".join(c.split("/")[:4]) for c in classes})[:80]
    info["resources"] = [n for n in names
                         if not n.endswith(".class") and not n.endswith("/")][:200]
    info["resource_kinds"] = dict(Counter(
        Path(n).suffix or "(none)" for n in names if not n.endswith("/")))
    try:
        man = z.read("META-INF/MANIFEST.MF").decode("utf-8", "replace")
        info["manifest"] = {k.strip(): v.strip() for k, _, v in
                            (l.partition(":") for l in man.splitlines() if ":" in l)}
    except KeyError:
        pass
    # plugin descriptors (ST plugins declare themselves via xml in META-INF or root)
    for cand in names:
        if cand.endswith(".xml") and ("plugin" in cand.lower() or "META-INF" in cand):
            info.setdefault("descriptors", []).append(cand)
    z.close()
    return info


def main() -> int:
    OUT.mkdir(exist_ok=True)
    jars = []
    for pattern in ("plugins/*.jar", "plugins/ip/*.jar", "utilities/**/*.jar",
                    "third_parties_plugins/**/*.jar", "Uninstaller/**/*.jar",
                    "db/**/*.jar", "jre/lib/*.jar"):
        for p in sorted(ROOT.glob(pattern)):
            jars.append(p)
    rows = []
    for p in jars:
        try:
            rows.append(jar_info(p))
        except Exception as exc:  # noqa: BLE001
            rows.append({"path": str(p), "error": str(exc)})
    (OUT / "jars.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    print(f"{len(rows)} jars -> analysis/jars.json")
    for r in rows[:40]:
        print(f"{r['bytes']:>9} {r.get('classes','-'):>5} {r.get('entries','-'):>5}  {r['path']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
