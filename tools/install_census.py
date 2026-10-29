"""Complete census of the installation tree: every directory, file type, and the
non-XML data formats CubeMX stores (databases, serialised state, caches).

For unusual extensions the tool sniffs the magic bytes so the format is
identified from evidence rather than guessed. Output: analysis/install_census.json.
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX")
OUT = Path(__file__).resolve().parent.parent / "analysis"

MAGIC = {
    b"\xca\xfe\xba\xbe": "java-class",
    b"PK\x03\x04": "zip/jar",
    b"\x7fELF": "elf",
    b"MZ": "pe",
    b"\x1f\x8b": "gzip",
    b"BZh": "bzip2",
    b"%PDF": "pdf",
    b"\xed\xab\xee\xdb": "rpm",
    b"SQLite format 3\x00": "sqlite3",
}

INTERESTING = {".pidx", ".mdbx", ".ser", ".dbx", ".plobl", ".bin", ".dat", ".index",
               ".json", ".csv", ".rl", ".policy", ".policyinfo", ".key", ".cer",
               ".der", ".pak", ".manifest", ".xsd", ".xsl", ".txt", ".properties"}


def sniff(path: Path) -> str:
    try:
        with path.open("rb") as fh:
            head = fh.read(16)
    except OSError:
        return "unreadable"
    for sig, kind in MAGIC.items():
        if head.startswith(sig):
            return kind
    if head[:5].isalpha() or head[:5] in (b"<?xml", b"{\\rtf"):
        return "text"
    try:
        head.decode("utf-8")
        return "text"
    except UnicodeDecodeError:
        return "binary"


def main() -> int:
    dirs: dict[str, dict] = {}
    ext_counts: dict[str, int] = defaultdict(int)
    ext_bytes: dict[str, int] = defaultdict(int)
    formats: dict[str, list[str]] = defaultdict(list)
    interesting: list[dict] = []
    total_files = 0
    total_bytes = 0
    for dirpath, dirnames, filenames in os.walk(ROOT, onerror=lambda e: None):
        dirnames[:] = [d for d in dirnames if d not in {"node_modules", "__pycache__"}]
        d = Path(dirpath)
        rel = str(d.relative_to(ROOT)).replace("\\", "/")
        rel = "." if rel == "." else rel
        row = dirs.setdefault(rel, {"files": 0, "bytes": 0, "kinds": defaultdict(int)})
        for fn in filenames:
            p = d / fn
            try:
                size = p.stat().st_size
            except OSError:
                continue
            total_files += 1
            total_bytes += size
            row["files"] += 1
            row["bytes"] += size
            ext = p.suffix.lower() or "(none)"
            ext_counts[ext] += 1
            ext_bytes[ext] += size
            row["kinds"][ext] += 1
            if ext in INTERESTING and size < 4_000_000:
                fmt = sniff(p)
                if ext not in (".json", ".txt", ".xsd", ".xsl", ".csv", ".properties"):
                    formats[fmt].append(f"{rel}/{fn}")
                interesting.append({"path": f"{rel}/{fn}", "bytes": size,
                                    "format": fmt})
    for row in dirs.values():
        row["kinds"] = dict(sorted(row["kinds"].items(), key=lambda x: -x[1]))
    report = {
        "root": str(ROOT),
        "total_files": total_files,
        "total_bytes": total_bytes,
        "directory_count": len(dirs),
        "extensions": dict(sorted(ext_counts.items(), key=lambda x: -x[1])),
        "extension_bytes": dict(sorted(ext_bytes.items(), key=lambda x: -x[1])[:40]),
        "detected_formats": {k: sorted(set(v))[:12] for k, v in sorted(formats.items())},
        "data_files": sorted(interesting, key=lambda r: -r["bytes"])[:300],
        "directories": {k: v for k, v in sorted(dirs.items())},
    }
    OUT.mkdir(exist_ok=True)
    (OUT / "install_census.json").write_text(json.dumps(report, indent=1),
                                             encoding="utf-8")
    print(f"{total_files} files, {total_bytes/1e6:.0f} MB, {len(dirs)} dirs")
    print("top extensions:", list(report["extensions"].items())[:14])
    print("formats:", {k: len(v) for k, v in report["detected_formats"].items()})
    print("largest data files:")
    for r in report["data_files"][:14]:
        print(f"   {r['bytes']:>10} {r['format']:12s} {r['path']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
