"""Fetch `pack status <json>` for a real MCU (N6) and reverse the component id
grammar, which is what `pack enable` filters must match.
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from mxmcp.engine import Session  # noqa: E402


def main() -> int:
    wd = pathlib.Path("probe/packstatus2").resolve()
    wd.mkdir(parents=True, exist_ok=True)
    s = Session(workdir=wd)
    out = wd / "st.json"
    s.send("load STM32F103C8Tx", timeout=180)
    r = s.send(f"pack status {out}", timeout=180)
    print("status:", r.status, r.seconds)
    s.close()
    data = json.loads(out.read_text(encoding="utf-8"))
    comps = []
    for model in data["models"]:
        for pack in model["packs"]:
            for comp in pack["components"]:
                comps.append(comp)
    print("components:", len(comps))
    # group by vendor:pack
    seen = {}
    for c in comps:
        parts = c["id"].split(":")
        key = f"{parts[0]}:{parts[1]}"
        seen.setdefault(key, c["id"])
    for k, v in sorted(seen.items()):
        print(f"{k}\n   {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
