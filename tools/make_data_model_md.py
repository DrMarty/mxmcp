"""Generate docs/DATA_MODEL.md from the analysis extracts.

Everything in the document is produced from `analysis/*.json`, so the numbers and
the vocabularies are evidence, not prose copied by hand.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
A = HERE / "analysis"
DST = HERE / "docs" / "DATA_MODEL.md"
load = lambda n: json.loads((A / n).read_text(encoding="utf-8"))


def table(rows, headers):
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(c).replace("\n", " ") for c in r) + " |")
    return "\n".join(out)


def main() -> int:
    db = load("db_schema.json")
    cond = load("condition_language.json")
    ioc = load("ioc_grammar.json")
    tpl = load("template_model.json")
    srv = load("cubeide_services.json")
    finder = load("mcufinder_data_layer.json")
    census = load("install_census.json")
    api = load("api_index.json")

    L: list[str] = ["# CubeMX Data Model (generated from installation artifacts and runtime extraction)", ""]
    L.append("This document is generated entirely by `tools/*.py` from forensic analysis of the "
             "installation and the running engine; the raw records are in `analysis/*.json`. "
             "Every field that is written back must be traceable to a source in this document.")
    L.append("")
    L.append("## 1. Asset Inventory")
    L.append(table(
        [(census["total_files"], f"{census['total_bytes']/1e6:.0f} MB",
          census["directory_count"],
          census["extensions"].get(".xml", 0), census["extensions"].get(".ftl", 0),
          census["extensions"].get(".ioc", 0), census["extensions"].get(".ld", 0),
          census["extensions"].get(".dtsi", 0) + census["extensions"].get(".dts", 0),
          len(api))
         for _ in range(1)],
        ["Files", "Size", "Directories", "XML", "FTL", "IOC", "LD", "DTS(I)", "Classes"]))
    L.append("")

    L.append("## 2. XML Families (root elements and element/attribute counts per family)")
    rows = []
    for group, info in db.items():
        if not isinstance(info, dict) or "elements" not in info:
            continue
        roots = ", ".join(f"{k}×{v}" for k, v in list(info["roots"].items())[:4])
        elems = ", ".join(f"{k}×{v}" for k, v in list(info["elements"].items())[:8])
        rows.append((group, info["files_total"], roots or "-", elems))
    L.append(table(rows, ["Directory family", "Files", "Root elements", "Frequent child elements"]))
    L.append("")

    L.append("## 3. MCU Record Fields (`db/mcu/*.xml`)")
    mcu = db["mcu"]
    attr_rows = []
    for el, attrs in list(mcu["attributes"].items())[:18]:
        keys = ", ".join(f"{k}×{v}" for k, v in list(attrs.items())[:8])
        attr_rows.append((el, keys))
    L.append(table(attr_rows, ["Element", "Attributes (occurrences)"]))
    L.append("")

    L.append("## 4. IP Mode Files (`db/mcu/IP/*_Modes.xml`)")
    ipm = db["mcu_ip_modes"]
    L.append(table([(el, n) for el, n in list(ipm["elements"].items())[:16]],
                   ["Element", "Occurrences in sample"]))
    L.append("")
    L.append("Observed value set of `RefParameter@Type` (including the vendor's hand-written spelling variants, all recorded as found):")
    L.append("```")
    L.append(", ".join(f"{k}×{v}" for k, v in sorted(
        cond["refparameter_types"].items(), key=lambda x: -x[1])[:26]))
    L.append("```")
    L.append("`PossibleValue@Action`: " + ", ".join(
        f"{k}×{v}" for k, v in sorted(cond["possiblevalue_actions"].items(),
                                      key=lambda x: -x[1])[:10]))
    L.append("")

    L.append("## 5. Condition Expression Language")
    L.append(f"- Total `Condition@Expression` count in sample: **{cond['condition_expressions']:,}"
             f"** ({cond['files']} files, {cond['parse_errors']} parse failures)")
    ops = [k for k in cond["operators_and_tokens"]
           if not k[0].isalpha() or k in ("true",)]
    L.append(f"- Operators/literals: `{'`, `'.join(ops[:12])}`")
    L.append(f"- Built-in references: `{'`, `'.join(list(cond['dollar_references'])[:8])}`")
    L.append(f"- Functions: `{'`, `'.join(list(cond['functions_used'])[:6])}`")
    L.append("- Semantics: `&` AND, `|` OR, `!` NOT, `=` equality, `>`/`<` comparison; "
             "`$IpInstance`/`$IpNumber` expand to the current instance; `Semaphore_*$IpInstance` is a resource semaphore; "
             "`DIE###` is a die-variant boolean; `OB_*` is an option-byte bit.")
    L.append("")

    L.append("## 6. `.ioc` Grammar (corpus statistics)")
    L.append(f"- Corpus: **{ioc['corpus_files']}** `.ioc` files, **{len(ioc['key_patterns'])}** key patterns; "
             f"families covered: {', '.join(ioc['families_in_corpus'][:14])} and others, "
             f"{len(ioc['families_in_corpus'])} in total.")
    top = list(ioc["key_patterns"].items())[:18]
    L.append(table([(k, v["count"], ", ".join(list(v["shapes"])[:3])) for k, v in top],
                   ["Key pattern", "Occurrences", "Value shapes"]))
    L.append("- Indexed list roots: " + ", ".join(ioc["indexed_list_roots"][:12]))
    L.append("- `:` inside values is escaped as `\\:`; `NVIC.<IRQ>` and `SH.*` are the most frequently escaped keys: " +
             ", ".join(ioc["escaped_value_keys"][:6]))
    L.append("")

    L.append("## 7. Code Generation Templates")
    L.append(f"- **{tpl['template_count']}** templates, **{len(tpl['model_keys'])}** model keys.")
    L.append("- Frequent model keys: " + ", ".join(f"`{k}`" for k in list(tpl["model_keys"])[:24]))
    L.append("- include graph (excerpt):")
    for k, v in list(tpl["include_graph"].items())[:5]:
        L.append(f"  - `{k}` → {', '.join(v[:6])}")
    L.append("")

    L.append("## 8. CubeIDE-MX Services (the actual backend for project/build generation)")
    rows = []
    for bundle, msgs in list(srv["services"].items()):
        names = sorted(k for k in msgs if k.endswith("Service"))
        rows.append((bundle.split("_")[0][:56], len(msgs), ", ".join(names[:8])))
    L.append(table(rows, ["p2 plugin", "Messages", "Service classes (excerpt)"]))
    L.append(f"- mxScratch schema: `{Path(srv['mxscratch_schema_file']).name if srv['mxscratch_schema_file'] else '-'}`, "
             f"root elements: {', '.join(e['name'] for e in srv['mxscratch_schema']['root_elements'][:12])} …")
    L.append("")

    L.append("## 9. Product Selection Database (`~/.stmcufinder/plugins/mcu/cube-finder-db.db`)")
    fdb = finder["finder_db"]
    if fdb.get("tables"):
        L.append(f"- {Path(fdb['path']).name}, {fdb['bytes']/1e6:.0f} MB, "
                 f"{len(fdb['tables'])} tables (read-only forensics)")
        L.append(table([(t, v["rows"], ", ".join(v["columns"])[:90])
                        for t, v in list(fdb["tables"].items())],
                       ["Table", "Rows", "Columns"]))
    else:
        L.append("- Not downloaded on this machine (obtained via a CubeMX database refresh)")
    L.append(f"- React↔Java bridge methods: {', '.join(sorted(finder['bridge_function_frequency']))}")
    L.append("")
    DST.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("wrote", DST.name, DST.stat().st_size, "bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
