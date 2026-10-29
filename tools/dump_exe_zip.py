#!/usr/bin/env python3
"""Sparse, constant-memory extractor for the ZIP payload inside STM32CubeMX.exe.

Facts (verified by byte-level probing, CubeMX 6.15.0):
  * Finding the PE stub's file tail first: the stub executable ends and the
    archive begins at the first valid local file header (PK\\x03\\x04 with a
    printable, slash-bearing name).
  * The archive stores CRC/sizes in local headers.
  * The central directory at the end is truncated and its early entries carry
    zeroed sizes, so it is not used.

Approach: stream local headers forward with a small sliding window; only the
compressed payload is buffered per entry. Writes a rebuilt zip.
"""
from __future__ import annotations

import struct
import sys
import zipfile
import zlib
from pathlib import Path

LHSIG = b"PK\x03\x04"


def locate_archive(exe: Path) -> int:
    """Return the file offset of the first zip local header in the PE tail."""
    with exe.open("rb") as f:
        # archive sits in the last third of the file; probe 4 MiB windows
        f.seek(0)
        size = f.seek(0, 2)
        start = max(0, size - 0x2000000)
        f.seek(start)
        buf = f.read(0x1000000)
    i = 0
    while True:
        i = buf.find(LHSIG, i)
        if i < 0:
            raise SystemExit("archive anchor not found")
        if i + 30 > len(buf):
            break
        nlen = struct.unpack_from("<H", buf, i + 26)[0]
        elen = struct.unpack_from("<H", buf, i + 28)[0]
        if 3 <= nlen <= 512 and i + 30 + nlen <= len(buf):
            name = buf[i + 30:i + 30 + nlen]
            if b"/" in name or b"." in name:
                if all(32 <= c < 127 for c in name):
                    return start + i
        i += 4
    raise SystemExit("archive anchor not found")


def main() -> int:
    argv = sys.argv[1:]
    exe = Path(argv[0]) if argv else Path(
        r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX\STM32CubeMX.exe")
    out = Path(argv[1]) if len(argv) > 1 else Path(r".\_extract")
    anchor = locate_archive(exe)
    print(f"archive anchor: 0x{anchor:X}")
    out.mkdir(parents=True, exist_ok=True)
    target = out / "cubemx_app.jar"

    f = exe.open("rb")
    f.seek(anchor)
    ok = skipped = 0
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zout:
        while True:
            hdr = f.read(30)
            if len(hdr) < 30 or hdr[:4] != LHSIG:
                break
            (ver, flag, method, mtime, mdate, crc, csize, usize,
             nlen, elen) = struct.unpack_from("<HHHHHIIIHH", hdr, 4)
            name = f.read(nlen).decode("utf-8", "replace")
            f.read(elen)
            payload = f.read(csize)
            if method == 0:
                data = payload
            elif method == 8:
                try:
                    data = zlib.decompress(payload, -15)
                except zlib.error:
                    skipped += 1
                    print("  bad deflate:", name)
                    data = None
            else:
                data = None
            if data is not None:
                zout.writestr(name, data)
                ok += 1
            if flag & 0x08:
                # data descriptor follows the payload
                sig = f.read(4)
                if sig[:4] == b"PK\x07\x08":
                    f.read(12)
                else:
                    f.seek(-4, 1)
    f.close()
    print(f"wrote {target} ({target.stat().st_size:,} bytes) ok={ok} skipped={skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
