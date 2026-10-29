"""MCUfinder web front-end: enumerate the local REST API the React app calls.

CubeMX embeds a JxBrowser-based React client (db/plugins/mcufinder/reactClient*)
that talks to an in-process HTTP server. This tool scans the shipped JS bundles
for endpoint paths, and the Java side for the handlers, so the whole selection
UI contract is documented (and callable from the MCP).
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
OUT = HERE / "analysis"
JAR = HERE / "_extract" / "cubemx_full.jar"

PATH_LIT = re.compile(r"[\"'`](/(?:api|rest|service|mcu|search|parametric|cross|cart|filter)[\w./{}-]{0,80})[\"'`]")
FETCH = re.compile(r"(?:fetch|axios\.\w+|get|post)\(\s*[\"'`]([^\"'`]{3,120})[\"'`]", re.I)
PORT = re.compile(r"(?:localhost|127\.0\.0\.1):(8\d{3}|9\d{3}|1\d{4})")


def js_files() -> list[tuple[Path, str]]:
    out = []
    for p in (ROOT / "db" / "plugins" / "mcufinder").rglob("*.js"):
        try:
            out.append((p, p.read_text(encoding="utf-8", errors="replace")))
        except OSError:
            pass
    return out


def java_handlers() -> dict[str, list[str]]:
    res: dict[str, list[str]] = {}
    if not JAR.exists():
        return res
    z = zipfile.ZipFile(JAR)
    lit = re.compile(r"^[A-Za-z0-9_\-/{}.]*(?:mcu|search|parametric|cross|cart|filter|api)[\w/.-]*$", re.I)
    for n in z.namelist():
        if not n.endswith(".class"):
            continue
        b = z.read(n)
        if b"com.st.microxplorer.mcufinder" not in n.encode() and b"http" not in b.lower():
            continue
        hits = set()
        for m in re.finditer(rb"[ -~]{5,120}", b):
            s = m.group().decode("ascii", "replace")
            if "/" in s and lit.fullmatch(s):
                hits.add(s)
        if hits:
            res[n[:-6].replace("/", ".")] = sorted(hits)[:40]
    return res


def main() -> int:
    OUT.mkdir(exist_ok=True)
    paths: collections.Counter = collections.Counter()
    ports: collections.Counter = collections.Counter()
    per_file: dict[str, list[str]] = {}
    for p, text in js_files():
        found = set()
        for m in PATH_LIT.finditer(text):
            found.add(m.group(1))
        for m in FETCH.finditer(text):
            s = m.group(1)
            if s.startswith("/") or "http" in s:
                found.add(s)
        for m in PORT.finditer(text):
            ports[m.group(0)] += 1
        if found:
            per_file[str(p.relative_to(ROOT)).replace("\\", "/")] = sorted(found)
            for f in found:
                paths[f] += 1
    report = {
        "js_files_scanned": len(per_file),
        "endpoints": dict(paths.most_common(200)),
        "host_ports": dict(ports),
        "per_bundle": per_file,
        "java_path_literals": java_handlers(),
    }
    (OUT / "mcufinder_api.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"bundles with endpoints: {len(per_file)}, distinct endpoints: {len(paths)}")
    for k in list(paths)[:40]:
        print("   ", k)
    print("ports:", list(ports)[:10])
    return 0


if __name__ == "__main__":
    sys.exit(main())
