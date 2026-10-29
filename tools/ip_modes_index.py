"""Offline mode catalogue: every IP's modes straight from the shipped db.

`get modes <IP>` returns KO for middleware IPs (their plugin answers only after
integration), so the only reliable source for "what modes may I enable" is
`db/mcu/IP/<IP>*_Modes.xml`. This tool indexes every such file into
`mxmcp/data/ip_modes.json`:

  { "FREERTOS": {"v8.0.0_Cube": ["CMSIS_V1","CMSIS_V2","Native"], …},
    "FATFS": {"v0.1.0_Cube": ["SDIO","USB","SRAM","FMC_SDRAM", …]}, … }

and also records the `IP@IPType` (peripheral / middleware) so callers know
whether `set mode` will register a `Mcu.IPn` entry.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX\db\mcu\IP")
HERE = Path(__file__).resolve().parent.parent
OUT = HERE / "analysis" / "ip_modes.json"
DATA = HERE / "mxmcp" / "data" / "ip_modes.json"


def _local(tag: str) -> str:
    return tag.split("}")[-1]


def _iter(root, name: str):
    """Iterate elements by local name, ignoring the MCU xml namespace."""
    for el in root.iter():
        if _local(el.tag) == name:
            yield el


def main() -> int:
    index: dict[str, dict] = {}
    for path in sorted(ROOT.glob("*_Modes.xml")):
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError:
            continue
        name = root.get("Name") or path.stem.split("-")[0]
        version = root.get("Version") or ""
        kind = root.get("IPType") or ""
        modes = []
        for ref in _iter(root, "RefMode"):
            m = ref.get("Name")
            if not m:
                continue
            modes.append({"name": m, "abstract": ref.get("Abstract") == "true",
                          "base": ref.get("BaseMode"), "group": ref.get("Group"),
                          "comment": (ref.get("Comment") or "")[:160]})
        for mode in _iter(root, "Mode"):
            m = mode.get("Name")
            if m and m not in [x["name"] for x in modes]:
                modes.append({"name": m, "abstract": False, "base": None,
                              "group": None,
                              "comment": (mode.get("UserName") or "")[:160]})
        params = []
        for rp in _iter(root, "RefParameter"):
            params.append({"name": rp.get("Name"), "type": rp.get("Type"),
                           "default": rp.get("DefaultValue"),
                           "group": rp.get("Group"),
                           "min": rp.get("Min"), "max": rp.get("Max")})
        entry = index.setdefault(name, {})
        entry[version or path.stem] = {
            "ip_type": kind, "file": path.name,
            "modes": [m["name"] for m in modes],
            "mode_details": [m for m in modes if not m["abstract"]],
            "parameters": params[:400]}
    OUT.write_text(json.dumps(index, indent=1), encoding="utf-8")
    DATA.parent.mkdir(exist_ok=True)
    flat = {k: sorted({m for v in d.values() for m in v["modes"]})
            for k, d in index.items()}
    DATA.write_text(json.dumps({"modes_by_ip": flat,
                                "detail": index}, indent=1), encoding="utf-8")
    print(f"{len(index)} IPs indexed, {len(flat)} with modes")
    for k in ("FREERTOS", "FATFS", "LWIP", "USB_DEVICE", "USB_HOST", "THREADX"):
        if k in flat:
            print(f"  {k:12s} {flat[k][:8]}")
    kinds = {}
    for d in index.values():
        for v in d.values():
            kinds[v["ip_type"]] = kinds.get(v["ip_type"], 0) + 1
    print("ip types:", kinds)
    return 0


if __name__ == "__main__":
    sys.exit(main())
