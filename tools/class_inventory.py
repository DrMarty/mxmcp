"""Bulk signature inventory for every com.st.* class shipped by CubeMX.

Runs `javap -p` over all classes of the rebuilt full jar and of every plugin jar,
parses the output into analysis/api_index.json:

  { "<jar>::<class>": {"extends": str, "interfaces": [..],
                       "methods": ["ret name(params)"], "fields": ["type name"] } }

This is the backbone for documenting the whole feature surface (plugin contracts,
IP model classes, generator, updater, security).
"""
from __future__ import annotations

import concurrent.futures as cf
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

JAVAP = r"C:\Program Files\Eclipse Adoptium\jdk-21.0.10.7-hotspot\bin\javap.exe"
HERE = Path(__file__).resolve().parent.parent
ROOT = Path(r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX")
JAR = HERE / "_extract" / "cubemx_full.jar"
OUT = HERE / "analysis"
PREFIX = "com/st/"
BATCH = 300

METHOD_RE = re.compile(r"^\s+(?:static\s+|final\s+|synchronized\s+|abstract\s+|native\s+|"
                       r"default\s+|public\s+|private\s+|protected\s+)*"
                       r"([\w$<>\[\].,? ]+?)\s+([\w$]+)\s*\(([^)]*)\)\s*(?:throws[^;{]*)?;?\s*$")
FIELD_RE = re.compile(r"^\s+(?:static\s+|final\s+|volatile\s+|transient\s+|public\s+|"
                      r"private\s+|protected\s+)*([\w$<>\[\].,?]+)\s+([\w$]+)\s*(?:=.*)?;\s*$")
HEADER_RE = re.compile(r"^\s*(.*?)\s+(class|interface|enum)(?:\s+([\w$.]+))?|"
                       r"^\s*(.*?)\s+(class|interface|enum)\s+([\w$.<>\[\]]+)"
                       r"(?:\s+extends\s+([\w$.<>\[\], ]+?))?"
                       r"(?:\s+implements\s+([\w$.<>\[\], ]+?))?\s*\{?")


def classes_of(jar: Path) -> list[str]:
    z = zipfile.ZipFile(jar)
    return sorted(n[:-6].replace("/", ".") for n in z.namelist()
                  if n.endswith(".class") and n.startswith(PREFIX)
                  and "$" not in n[len(PREFIX):].split("/")[-1])


def parse(text: str) -> dict:
    """Split a multi-class javap dump into per-class records."""
    out: dict[str, dict] = {}
    current = None
    for line in text.splitlines():
        if line.startswith("Compiled from"):
            continue
        m = re.match(r"^\s*(public|final|abstract)?\s*(class|interface|enum)\s+"
                     r"([\w$.]+)(?:\s+extends\s+([\w$.<>\[\], ]+?))?"
                     r"(?:\s+implements\s+([\w$.<>\[\], ]+?))?\s*\{?\s*$", line)
        if m:
            current = m.group(3)
            out[current] = {"extends": (m.group(4) or "").strip(),
                            "interfaces": [x.strip() for x in (m.group(5) or "").split(",")
                                           if x.strip()],
                            "methods": [], "fields": [], "kind": m.group(2)}
            continue
        if current is None:
            continue
        if line.strip() == "}":
            current = None
            continue
        mm = METHOD_RE.match(line.rstrip().rstrip("{").strip() + ";"
                             if not line.rstrip().endswith(";") else line.rstrip())
        if mm and "(" in line:
            ret, name, args = mm.groups()
            ret = ret.strip()
            if ret in ("class", "interface", "enum") or name in ("if", "for", "while"):
                continue
            out[current]["methods"].append(f"{ret} {name}({args.strip()})")
            continue
        fm = FIELD_RE.match(line.rstrip())
        if fm:
            typ, name = fm.groups()
            out[current]["fields"].append(f"{typ.strip()} {name}")
    return out


def run_batch(jar: Path, names: list[str]) -> dict:
    args = [JAVAP, "-p", "-cp", str(jar)] + names
    p = subprocess.run(args, capture_output=True, timeout=600)
    return parse(p.stdout.decode("utf-8", "replace"))


def main() -> int:
    OUT.mkdir(exist_ok=True)
    jars = [JAR] + [p for p in sorted((ROOT / "plugins").glob("*.jar"))] + \
        [p for p in sorted((ROOT / "plugins" / "ip").glob("*.jar"))]
    index: dict[str, dict] = {}
    for jar in jars:
        try:
            names = classes_of(jar)
        except Exception as exc:  # noqa: BLE001
            print("skip", jar, exc)
            continue
        if not names:
            continue
        key = "app" if jar == JAR else jar.name
        batches = [names[i:i + BATCH] for i in range(0, len(names), BATCH)]
        rows: dict[str, dict] = {}
        with cf.ThreadPoolExecutor(max_workers=6) as ex:
            for res in ex.map(lambda b: run_batch(jar, b), batches):
                rows.update(res)
        for cls, rec in rows.items():
            index[f"{key}::{cls}"] = rec
        print(f"{key}: {len(names)} classes -> {len(rows)} parsed", flush=True)
    (OUT / "api_index.json").write_text(json.dumps(index, indent=1), encoding="utf-8")
    print(f"total classes {len(index)} -> analysis/api_index.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
