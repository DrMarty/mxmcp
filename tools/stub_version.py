"""Parse the RT_VERSION resource of the CubeMX native stub (build identity)."""
from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

EXE = Path(r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX\STM32CubeMX.exe")
OUT = Path(__file__).resolve().parent.parent / "analysis" / "stub_version.json"


def align4(n: int) -> int:
    return (n + 3) & ~3


def parse(node: bytes, pos: int, acc: dict, depth: int = 0) -> int:
    """Walk one VS_VERSION_INFO block tree; return the offset after it."""
    if pos + 6 > len(node):
        return pos
    length, valu_len, vtype = struct.unpack_from("<HHH", node, pos)
    if length == 0:
        return pos
    end = pos + length
    key_start = pos + 6
    raw = node[key_start:end]
    key = raw.split(b"\x00\x00", 1)[0].decode("utf-16-le", "replace")
    if vtype == 0:  # binary VS_FIXEDFILEINFO
        fi = align4(key_start + len(key) * 2 + 2)
        if valu_len >= 52 and fi + 52 <= end:
            (sig, _, fms, fls, pms, pls) = struct.unpack_from("<IIHHHH", node, fi)
            acc["fixed"] = {
                "signature": hex(sig),
                "file_version": f"{fms >> 16}.{fms & 0xffff}.{fls >> 16}.{fls & 0xffff}",
                "product_version": f"{pms >> 16}.{pms & 0xffff}.{pls >> 16}.{pls & 0xffff}",
            }
    else:
        val_start = align4(key_start + len(key) * 2 + 2)
        if valu_len and val_start + valu_len <= end:
            data = node[val_start:val_start + valu_len]
            if vtype == 1:
                acc.setdefault("strings", {})[key] = data.decode("utf-16-le", "replace")
                if valu_len == 4:
                    hi, lo = struct.unpack("<HH", data)
                    acc.setdefault("numbers", {})[key] = [hi >> 16, hi & 0xffff,
                                                          lo >> 16, lo & 0xffff]
    after_key = align4(key_start + len(key) * 2 + 2)
    child = align4(after_key + valu_len)
    while child + 6 <= end:
        sl = struct.unpack_from("<H", node, child)[0]
        if sl == 0 or child + sl > end:
            break
        parse(node, child, acc, depth + 1)
        child = align4(child + sl)
    return end


def main() -> int:
    data = EXE.read_bytes()
    # VS_VERSION_INFO is stored UTF-16 inside the RT_VERSION resource
    needle = "VS_VERSION_INFO".encode("utf-16-le")
    blocks = []
    i = data.find(needle, 0, 300_000)
    while i > 0:
        start = i - 6
        acc: dict = {}
        try:
            parse(data, start, acc)
        except Exception as exc:  # noqa: BLE001
            acc["error"] = str(exc)
        if acc:
            blocks.append({"offset": start, **acc})
        i = data.find(needle, i + 1)
    OUT.write_text(json.dumps({"exe": str(EXE), "blocks": blocks}, indent=1),
                   encoding="utf-8")
    for b in blocks:
        print("== offset", b["offset"], b.get("fixed", {}))
        for k, v in (b.get("strings") or {}).items():
            print(f"   {k:28s} = {v[:80]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
