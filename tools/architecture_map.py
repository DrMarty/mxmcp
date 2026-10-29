"""Package-level architecture map for the CubeMX application.

Uses analysis/api_index.json to summarise every `com.st.**` package: class count,
public interfaces, key classes (by name heuristics), and the classes each package
depends on (from method/field signatures). Emits analysis/architecture.json and a
markdown table used by the docs.
"""
from __future__ import annotations

import collections
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
OUT = HERE / "analysis"
API = json.loads((OUT / "api_index.json").read_text(encoding="utf-8"))

THIRD_PARTY_PREFIXES = ("com.st.components.", "com.st.microxplorer.", "com.st.tools.",
                        "com.st.ipmodeconfigmanager.", "com.st.laws.", "com.st.util.",
                        "com.st.log.", "com.st.stm32cube.", "com.st.sw4stm32.")


def pkg_of(cls: str) -> str:
    return cls.rsplit(".", 1)[0] if "." in cls else "(default)"


def main() -> int:
    per_pkg: dict[str, dict] = {}
    edges: collections.Counter = collections.Counter()
    for key, rec in API.items():
        jar, cls = key.split("::", 1)
        pkg = pkg_of(cls)
        row = per_pkg.setdefault(pkg, {"jar": jar, "classes": 0, "interfaces": 0,
                                       "methods": 0, "fields": 0,
                                       "notable": [], "deps": collections.Counter()})
        row["classes"] += 1
        if rec["kind"] == "interface":
            row["interfaces"] += 1
        row["methods"] += len(rec["methods"])
        row["fields"] += len(rec["fields"])
        simple = cls.rsplit(".", 1)[-1]
        if re.search(r"(Manager|Engine|Generator|Service|Controller|View|Loader|"
                     r"Factory|Constants|Interface|Cli|Builder|Checker|Handler|"
                     r"Parser|Model|Db|DB)", simple):
            if len(row["notable"]) < 25:
                row["notable"].append(simple)
        blob = " ".join(rec["methods"]) + " " + " ".join(rec["fields"])
        for dep in set(re.findall(r"\b(com\.st\.[\w.]+)", blob)):
            dp = pkg_of(dep)
            if dp != pkg and dp.startswith(THIRD_PARTY_PREFIXES):
                edges[f"{pkg} -> {dp}"] += 1
                row["deps"][dp] += 1
    for row in per_pkg.values():
        row["deps"] = dict(row["deps"].most_common(12))
    report = {
        "packages": {k: v for k, v in sorted(per_pkg.items())},
        "package_count": len(per_pkg),
        "class_count": len(API),
        "dependency_edges": dict(edges.most_common(400)),
    }
    (OUT / "architecture.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"{len(per_pkg)} packages, {len(API)} classes, {len(edges)} edges")
    top = sorted(per_pkg.items(), key=lambda kv: -kv[1]["methods"])[:20]
    for pkg, v in top:
        print(f"  {v['methods']:6d} methods {v['classes']:4d} cls  {pkg}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
