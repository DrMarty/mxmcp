"""Bulk signature inventory for every com.st.* class shipped by CubeMX.

Runs `javap -p` over all top-level classes of the rebuilt full jar and of every
plugin jar, and parses the output into analysis/api_index.json:

  { "<jar>::<class>": {"kind","extends","interfaces",
                       "methods": ["ret name(params)"], "fields": ["type name"]} }

Constructors are kept as `name(params)`. This index is the backbone of the
feature documentation (plugin contracts, IP model, generator, updater, security).
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
PREFIXES = ("com/st/", "com/cygnus/", "com/stmicroelectronics/")
BATCH = 250
MODIFIERS = ("public", "private", "protected", "static", "final", "abstract",
             "synchronized", "native", "transient", "volatile", "default", "strictfp")

CLASS_RE = re.compile(r"^(?:(?:public|final|abstract|static)\s+)*"
                      r"(class|interface|enum|@interface)\s+([\w$.]+)"
                      r"(?:<[^>]*>)?"
                      r"(?:\s+extends\s+([\w$.<>\[\], ?]+?))?"
                      r"(?:\s+implements\s+([\w$.<>\[\], ?]+?))?\s*\{?$")


def _split_type_and_name(head: str) -> tuple[str, str]:
    """'java.lang.String foo' -> ('java.lang.String','foo'); 'Foo' -> ('','Foo')."""
    head = head.strip()
    if not head:
        return "", ""
    parts = head.rsplit(" ", 1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return "", head


def parse(text: str) -> dict:
    out: dict[str, dict] = {}
    current: dict | None = None
    current_simple = ""
    for raw in text.splitlines():
        line = raw.rstrip()
        s = line.strip()
        if not s or s.startswith("Compiled from"):
            continue
        m = CLASS_RE.match(s)
        if m:
            kind, name = m.group(1), m.group(2)
            current = {"kind": kind,
                       "extends": (m.group(3) or "").strip(),
                       "interfaces": [x.strip() for x in (m.group(4) or "").split(",")
                                      if x.strip()],
                       "methods": [], "fields": []}
            out[name] = current
            current_simple = name.split(".")[-1]
            continue
        if current is None:
            continue
        if s in ("}", "};"):
            current = None
            continue
        if s.startswith("Code:") or s.startswith("static {") or s.startswith("{"):
            continue
        body = s.rstrip(";").strip()
        toks = body.split()
        while toks and toks[0] in MODIFIERS:
            toks = toks[1:]
        body = " ".join(toks)
        if not body:
            continue
        if "(" in body and (body.endswith(")") or ") throws" in body):
            head, _, rest = body.partition("(")
            args = rest.split(")")[0].strip()
            ret, name = _split_type_and_name(head)
            if not name:
                continue
            if name == current_simple:
                ret = ""                       # constructor
            elif ret == "":
                continue                       # bare word, not a signature
            current["methods"].append(f"{ret} {name}({args})".strip())
            continue
        typ, name = _split_type_and_name(body)
        if name and typ:
            current["fields"].append(f"{typ} {name}")
    return out


def classes_of(jar: Path) -> list[str]:
    z = zipfile.ZipFile(jar)
    names = []
    for n in z.namelist():
        if not n.endswith(".class"):
            continue
        if not n.startswith(PREFIXES):
            continue
        simple = n.rsplit("/", 1)[-1]
        if "$" in simple:
            continue
        names.append(n[:-6].replace("/", "."))
    return sorted(names)


def run_batch(jar: Path, names: list[str]) -> dict:
    p = subprocess.run([JAVAP, "-p", "-cp", str(jar)] + names,
                       capture_output=True, timeout=900)
    return parse(p.stdout.decode("utf-8", "replace"))


def main() -> int:
    OUT.mkdir(exist_ok=True)
    jars = [JAR] + sorted((ROOT / "plugins").glob("*.jar")) + \
        sorted((ROOT / "plugins" / "ip").glob("*.jar")) + \
        sorted((ROOT / "utilities").glob("**/*.jar"))
    index: dict[str, dict] = {}
    for jar in jars:
        try:
            names = classes_of(jar)
        except Exception as exc:  # noqa: BLE001
            print("skip", jar, exc, flush=True)
            continue
        if not names:
            continue
        key = "app" if jar == JAR else jar.name
        batches = [names[i:i + BATCH] for i in range(0, len(names), BATCH)]
        rows: dict[str, dict] = {}
        with cf.ThreadPoolExecutor(max_workers=8) as ex:
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
