"""Code-generation template model extraction.

Scrapes every FreeMarker template shipped with CubeMX (db/templates,
db/extra_templates, db/plugins/*) for:
  * `${expr}` / `#{expr}` interpolations, split into root identifier + path
  * `<#assign name = expr>` bindings
  * `<#if ...>` / `<#list ...>` / `<#recover>` conditions
  * `<@directive ...>` custom tags
  * `<#import|include "x">` include graph
  * functions/macros defined locally

Output analysis/template_model.json gives the complete variable surface the
generator exposes (the data contract between the Java IP model and the .c/.h
output), plus which templates define/consume which keys.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX\db")
HERE = Path(__file__).resolve().parent.parent
OUT = HERE / "analysis"

INTERP = re.compile(r"[#$]\{\s*([^{}]*?)\s*\}")
ASSIGN = re.compile(r"<#assign\s+(\w+)\s*=\s*(.*?)\s*/>")
LISTDIR = re.compile(r"<#list\s+(.*?)\s+as\s+(\w+)")
IFDIR = re.compile(r"<#if\s+(.*?)>", re.S)
MACRO = re.compile(r"<#macro\s+(\w+)")
FUNC = re.compile(r"<#function\s+(\w+)")
CALL = re.compile(r"<@(\w+)")
IMPORT = re.compile(r"<#include\s+\"([^\"]+)\"|<#import\s+\"([^\"]+)\"")
TERNARY = re.compile(r"\?\w+")


def roots(expr: str) -> list[str]:
    """Root identifiers of a FreeMarker expression."""
    out = []
    for m in re.finditer(r"(?<![\w.$])([A-Za-z_]\w*)", expr):
        tok = m.group(1)
        if tok in {"if", "else", "true", "false", "and", "or", "not", "in",
                   "string", "number", "boolean", "seq", "hash", "exists",
                   "is_string", "is_number", "then", "default", "size",
                   "cap_first", "lower_case", "upper_case", "join", "split",
                   "replace", "index_of", "contains", "length", "int", "sort"}:
            continue
        out.append(tok)
    return out


def main() -> int:
    OUT.mkdir(exist_ok=True)
    templates = sorted(ROOT.rglob("*.ftl"))
    print(f"{len(templates)} templates")
    keys: Counter = Counter()
    paths: Counter = Counter()
    per_file: dict[str, dict] = {}
    macros: Counter = Counter()
    calls: Counter = Counter()
    imports: dict[str, list[str]] = {}
    assigns: Counter = Counter()
    conditions: Counter = Counter()
    lists: Counter = Counter()
    for t in templates:
        try:
            text = t.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = str(t.relative_to(ROOT)).replace("\\", "/")
        exprs = [m.group(1) for m in INTERP.finditer(text)]
        rs: Counter = Counter()
        for e in exprs:
            path = e.split("?")[0].strip()
            rts = roots(path)
            if rts:
                rs[rts[0]] += 1
                keys[rts[0]] += 1
            if "." in path:
                paths[path[:80]] += 1
        for m in ASSIGN.finditer(text):
            assigns[m.group(1)] += 1
        for m in MACRO.finditer(text):
            macros[m.group(1)] += 1
        for m in FUNC.finditer(text):
            macros[f"function:{m.group(1)}"] += 1
        for m in CALL.finditer(text):
            calls[m.group(1)] += 1
        for m in LISTDIR.finditer(text):
            lists[m.group(1)[:70]] += 1
        for m in IFDIR.finditer(text):
            cond = " ".join(m.group(1).split())[:90]
            if len(cond) < 90:
                conditions[cond] += 1
        imps = [a or b for a, b in IMPORT.findall(text)]
        if imps:
            imports[rel] = imps
        per_file[rel] = {
            "bytes": t.stat().st_size,
            "interpolations": len(exprs),
            "roots": dict(rs.most_common(40)),
            "macros_defined": [m.group(1) for m in MACRO.finditer(text)],
            "functions_defined": [m.group(1) for m in FUNC.finditer(text)],
            "assigns": [m.group(1) for m in ASSIGN.finditer(text)][:40],
            "imports": imps,
        }
    report = {
        "template_count": len(templates),
        "model_keys": dict(keys.most_common(600)),
        "model_paths": dict(paths.most_common(600)),
        "assigns": dict(assigns.most_common(300)),
        "macros": dict(macros.most_common(200)),
        "directive_calls": dict(calls.most_common(200)),
        "list_sources": dict(lists.most_common(200)),
        "conditions": dict(conditions.most_common(300)),
        "include_graph": imports,
        "per_template": per_file,
    }
    (OUT / "template_model.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"{len(keys)} model keys, {len(macros)} macros, {len(per_file)} templates")
    print("top model keys:", [k for k, _ in keys.most_common(30)])
    return 0


if __name__ == "__main__":
    sys.exit(main())
