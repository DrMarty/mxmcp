"""Slim the config model down to what code generation actually needs.

The full extraction is 72 MB because it keeps every comment, file list and
family duplicate. The generator only needs, per IP and family:
  * the `LibMethod` argument tree (name/generic/type/address_of/optimize)
  * the `RefConfig` call sequence (which method is called, with which parameters)
That trims to a few MB and compresses well inside the pack.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
SRC = HERE / "analysis" / "config_model.json"
OUT = HERE / "mxmcp" / "data" / "config_slim.json"


def slim_args(args: list[dict]) -> list[dict]:
    out = []
    for a in args:
        item = {"n": a.get("name", ""), "g": a.get("generic", "")}
        if a.get("type"):
            item["t"] = a["type"]
        if a.get("address_of"):
            item["a"] = 1
        if a.get("optimize"):
            item["o"] = a["optimize"]
        if a.get("condition"):
            item["c"] = a["condition"]
        kids = slim_args(a.get("children") or [])
        if kids:
            item["k"] = kids
        out.append(item)
    return out


def main() -> int:
    data = json.loads(SRC.read_text(encoding="utf-8"))
    out: dict[str, dict] = {}
    for ip, families in data.items():
        # one variant per family is enough: keep the shortest family key so
        # STM32F1xx and STM32F1xx_128 collapse predictably
        fams = {}
        for fam, rec in families.items():
            base = fam.split("_")[0]
            if base in fams:
                continue
            fams[base] = {
                "methods": {name: slim_args(m.get("arguments") or [])
                            for name, m in (rec.get("lib_methods") or {}).items()},
                "configs": {name: [{"k": c["kind"], "n": c["name"],
                                    "a": [x["name"] for x in c.get("args") or []]}
                                   for c in (cfg.get("calls") or [])]
                            for name, cfg in (rec.get("configs") or {}).items()},
            }
        out[ip] = fams
    OUT.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    size = OUT.stat().st_size
    methods = sum(len(f["methods"]) for v in out.values() for f in v.values())
    print(f"{len(out)} IPs, {methods} methods, {size/1e6:.1f} MB -> {OUT}")
    for ip in ("USART", "GPIO", "ADC"):
        if ip in out:
            fam = sorted(out[ip])[0]
            print(f"  {ip}[{fam}] methods={list(out[ip][fam]['methods'])[:6]}")
            us = out[ip][fam]["methods"].get("HAL_USART_Init") or \
                out[ip][fam]["methods"].get("HAL_GPIO_Init")
            if us:
                print(f"      args={[a['n'] for a in us][:10]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
