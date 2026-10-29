"""Full-corpus grammar of the IP mode/parameter condition language.

Scans every db/mcu/IP/*_Modes.xml and db/mcu/config/*_Configs.xml (2 600+ files)
and derives:
  * the set of operators/functions/tokens used in `Condition@Expression`
  * how identifiers are referenced (plain parameter, `$IpNumber`, `$IpInstance`,
    die names, pin signals, `<PARAM>` placeholders)
  * the vocabulary of `PossibleValue@Action`, `RefParameter@Type`, `Group`, `Unit`
  * per-IP counts (which IPs use conditions most heavily)

Output: analysis/condition_language.json — the spec the MCP uses to explain why a
parameter/mode is unavailable (CubeMX's `check`/diagnostics mirror this).
"""
from __future__ import annotations

import collections
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX\db\mcu")
OUT = Path(__file__).resolve().parent.parent / "analysis"

TOKEN = re.compile(r"[A-Za-z_$][\w$.]*|\(|\)|&|\||!|=|<|>|,|;|\+|-|\*|/|\?|:")
DOLLAR = re.compile(r"\$\{?\w+\}?")
CMP = re.compile(r"([A-Za-z_$][\w$.]*)\s*(=|!=|<|>|<=|>=)\s*([^\s&|)!]+)")
FUNC_CALL = re.compile(r"([A-Za-z_]\w*)\s*\(")


def strip_ns(tag: str) -> str:
    return tag.split("}")[-1]


def main() -> int:
    files = sorted((ROOT / "IP").glob("*.xml")) + sorted((ROOT / "config").glob("*.xml"))
    print(f"{len(files)} mode/config files")
    tokens: collections.Counter = collections.Counter()
    comparisons: collections.Counter = collections.Counter()
    rvalues: collections.Counter = collections.Counter()
    funcs: collections.Counter = collections.Counter()
    dollars: collections.Counter = collections.Counter()
    actions: collections.Counter = collections.Counter()
    types: collections.Counter = collections.Counter()
    groups: collections.Counter = collections.Counter()
    units: collections.Counter = collections.Counter()
    per_ip: collections.Counter = collections.Counter()
    element_names: collections.Counter = collections.Counter()
    attribute_names: collections.Counter = collections.Counter()
    expr_total = 0
    errors = 0
    for f in files:
        try:
            tree = ET.parse(f)
        except ET.ParseError:
            errors += 1
            continue
        root = tree.getroot()
        ipname = root.get("Name", f.stem.split("-")[0])
        for el in root.iter():
            t = strip_ns(el.tag)
            element_names[t] += 1
            for k, v in el.attrib.items():
                attribute_names[f"{t}@{k}"] += 1
            expr = el.get("Expression") or el.get("OptimizationCondition") or ""
            expr = expr.strip()
            if expr:
                expr_total += 1
                per_ip[ipname] += 1
                for tok in TOKEN.findall(expr):
                    tokens[tok] += 1
                for m in CMP.finditer(expr):
                    comparisons[f"{m.group(1)} {m.group(2)}"] += 1
                    rvalues[m.group(3)] += 1
                for m in FUNC_CALL.finditer(expr):
                    funcs[m.group(1)] += 1
                for m in DOLLAR.finditer(expr):
                    dollars[m.group(0)] += 1
            if t == "PossibleValue" and el.get("Action"):
                actions[el.get("Action")] += 1
            if t == "RefParameter":
                types[el.get("Type", "")] += 1
                groups[el.get("Group", "")] += 1
                units[el.get("Unit", "")] += 1
    report = {
        "files": len(files), "parse_errors": errors,
        "condition_expressions": expr_total,
        "operators_and_tokens": dict(tokens.most_common(80)),
        "dollar_references": dict(dollars.most_common(40)),
        "functions_used": dict(funcs.most_common(40)),
        "comparison_targets": dict(comparisons.most_common(120)),
        "comparison_values": dict(rvalues.most_common(120)),
        "possiblevalue_actions": dict(actions),
        "refparameter_types": dict(types),
        "refparameter_groups": {k: v for k, v in groups.most_common(80)},
        "refparameter_units": {k: v for k, v in units.most_common(40) if k},
        "elements": dict(element_names.most_common(80)),
        "attributes": dict(attribute_names.most_common(200)),
        "top_ips_by_conditions": dict(per_ip.most_common(60)),
    }
    OUT.mkdir(exist_ok=True)
    (OUT / "condition_language.json").write_text(json.dumps(report, indent=1),
                                                 encoding="utf-8")
    print("expressions:", expr_total, "parse errors:", errors)
    print("tokens:", list(report["operators_and_tokens"])[:20])
    print("functions:", list(report["functions_used"])[:15])
    print("dollar refs:", list(report["dollar_references"])[:15])
    return 0


if __name__ == "__main__":
    sys.exit(main())
