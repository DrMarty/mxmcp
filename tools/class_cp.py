"""Minimal class-file constant-pool reader (no external deps).

Used to inspect CubeMX classes without javap, because one toolchain path
produces truncated dumps for very large methods.
"""
from __future__ import annotations

import struct
import sys
import zipfile
from pathlib import Path

JAR = Path(r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX\plugins\thirdparty.jar")


def strings_of(class_bytes: bytes) -> list[str]:
    assert class_bytes[:4] == b"\xca\xfe\xba\xbe"
    count = struct.unpack_from(">H", class_bytes, 8)[0]
    pos = 10
    out: list[str] = []
    i = 1
    while i < count:
        tag = class_bytes[pos]
        pos += 1
        if tag == 1:  # Utf8
            ln = struct.unpack_from(">H", class_bytes, pos)[0]
            pos += 2
            raw = class_bytes[pos:pos + ln]
            pos += ln
            try:
                out.append(raw.decode("utf-8"))
            except UnicodeDecodeError:
                out.append(raw.decode("latin-1"))
        elif tag in (7, 8, 16, 19, 20):
            pos += 2
        elif tag == 15:
            pos += 3
        elif tag in (3, 4, 9, 10, 11, 12, 17, 18):
            pos += 4
        elif tag in (5, 6):
            pos += 8
            i += 1
        else:
            raise ValueError(f"bad cp tag {tag} at {pos}")
        i += 1
    return out


def main() -> int:
    cls = sys.argv[1] if len(sys.argv) > 1 else \
        "com/st/microxplorer/plugins/thirdparty/engine/PackLoader.class"
    z = zipfile.ZipFile(JAR)
    data = z.read(cls)
    for s in strings_of(data):
        if any(k in s for k in ("not found", "database", "opulate", "repository")):
            print(repr(s))
    return 0


if __name__ == "__main__":
    sys.exit(main())
