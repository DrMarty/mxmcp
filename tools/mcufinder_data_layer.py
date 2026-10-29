"""Document the MCU-finder data layer: the Java bridge API and the SQLite catalog.

CubeMX's parametric selector runs a React UI inside JxBrowser that calls back into
Java through `window.java.<method>(...)`, and queries a local SQLite database
(`~/.stmcufinder/plugins/mcu/cube-finder-db.db`, downloaded from
https://sw-center.st.com/packs/cube-finder-db/md5.xml).

This tool:
  * enumerates every `window.java.*` call site in the shipped bundles
  * reads api_config.json (server endpoints used by that UI)
  * dumps the SQLite schema + row counts of the finder database

Output: analysis/mcufinder_data_layer.json
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX")
HOME = Path.home()
OUT = Path(__file__).resolve().parent.parent / "analysis" / "mcufinder_data_layer.json"

BRIDGE = re.compile(r"window\.java\.([A-Za-z_]\w*)\s*\(")
BRIDGE_PROP = re.compile(r"window\.java\.([A-Za-z_]\w*)")


def bridge_calls() -> dict:
    res: dict[str, list[str]] = {}
    for d in ("reactClient", "reactClient1"):
        base = ROOT / "db" / "plugins" / "mcufinder" / d
        if not base.exists():
            continue
        for p in sorted(base.rglob("*.js")):
            text = p.read_text(encoding="utf-8", errors="replace")
            calls = sorted(set(BRIDGE.findall(text)))
            props = sorted(set(BRIDGE_PROP.findall(text)) - set(calls))
            if calls or props:
                res[f"{d}/{p.name}"] = {"functions": calls, "properties": props}
    return res


def api_config() -> dict:
    for p in (HOME / ".stmcufinder" / "plugins" / "mcufinder" / "mcu" / "api_config.json",
              ROOT / "db" / "plugins" / "mcufinder" / "mcu" / "api_config.json"):
        if p.exists():
            return {"path": str(p), "json": json.loads(p.read_text(encoding="utf-8"))}
    return {"path": None}


def finder_db() -> dict:
    cands = [HOME / ".stmcufinder" / "plugins" / "mcufinder" / "mcu" / "cube-finder-db.db",
             ROOT / "db" / "plugins" / "mcufinder" / "mcu" / "cube-finder-db.db"]
    db = next((c for c in cands if c.exists()), None)
    if not db:
        return {"path": None}
    out: dict = {"path": str(db), "bytes": db.stat().st_size, "tables": {}}
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    cur = con.cursor()
    names = [r[0] for r in cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    for t in names:
        try:
            cnt = cur.execute(f"SELECT COUNT(*) FROM '{t}'").fetchone()[0]
        except sqlite3.Error:
            cnt = -1
        cols = [f"{r[1]}:{r[2]}" for r in cur.execute(f"PRAGMA table_info('{t}')")]
        out["tables"][t] = {"rows": cnt, "columns": cols}
    fk = [r for r in cur.execute("PRAGMA foreign_key_list('parametric_value')")] \
        if "parametric_value" in names else []
    out["foreign_keys_parametric_value"] = fk
    con.close()
    return out


def md5_and_mfd() -> dict:
    res = {}
    for name in ("md5.xml", "mcuFinder.mfd", "tutoVideoDB.json", "mcusAds.json"):
        for base in (HOME / ".stmcufinder" / "plugins" / "mcufinder" / "mcu",
                     ROOT / "db" / "plugins" / "mcufinder" / "mcu"):
            p = base / name
            if p.exists():
                txt = p.read_text(encoding="utf-8", errors="replace")
                res[name] = {"path": str(p), "bytes": p.stat().st_size,
                             "head": txt[:600]}
                break
    return res


def user_state() -> dict:
    d = HOME / ".stm32cubemx"
    out = {}
    if d.exists():
        for f in ("cad_preferences.json", "mxinstallversion.txt", "favorites.mcus.txt",
                  "favorites.boards.txt", "log4j2.xml"):
            p = d / f
            if p.exists():
                out[f] = p.read_text(encoding="utf-8", errors="replace")[:1200]
        prefs = d / "ThirdParty.prefs"
        if prefs.exists():
            out["ThirdParty.prefs"] = prefs.read_text(encoding="utf-8",
                                                      errors="replace")[:1500]
    return out


def main() -> int:
    report = {
        "bridge_calls": bridge_calls(),
        "api_config": api_config(),
        "finder_db": finder_db(),
        "catalog_files": md5_and_mfd(),
        "user_state_files": user_state(),
    }
    totals = Counter()
    for v in report["bridge_calls"].values():
        totals.update(v["functions"])
    report["bridge_function_frequency"] = dict(totals.most_common(200))
    OUT.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print("bridge functions:", len(totals))
    print(sorted(totals)[:60])
    db = report["finder_db"]
    if db.get("tables"):
        print(f"finder db: {len(db['tables'])} tables, {db['bytes']/1e6:.0f} MB")
        for t, v in list(db["tables"].items())[:12]:
            print(f"   {t:32s} rows={v['rows']:7d} cols={len(v['columns'])}")
    else:
        print("finder db: not present locally")
    return 0


if __name__ == "__main__":
    sys.exit(main())
