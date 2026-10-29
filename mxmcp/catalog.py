"""Offline catalog over the CubeMX database (no engine needed).

Verified layout (CubeMX 6.15.0):

  db/mcu/<RefName>.xml        attributes: Family, Line, Package, RefName, ClockTree,
                              DBVersion; children Core/Frequency/Ram/IONb/Die/
                              Flash*/Voltage/Current/Temperature/IP*/Pin*
  db/mcu/families.xml         family tree (used for grouping)
  db/mcu/memory/*.xml         die level flash/RAM geometry (indexed by <Die>)
  db/plugins/boardmanager/    *.pdsc board lists + preconfigured *.ioc per board
  db/mcu/IP/*_Cube_Modes.xml  IP mode trees
  db/mcu/config/*_Configs.xml per-IP parameter definitions
  db/templates/*.ftl          FreeMarker code templates

Everything here is read-only and cached; it never starts the Java engine.
"""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_ROOT = Path(r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX")
NS = "{http://mcd.rou.st.com/modules.php?name=mcu}"


@dataclass
class McuInfo:
    ref_name: str
    family: str = ""
    line: str = ""
    package: str = ""
    core: str = ""
    freq_mhz: str = ""
    ram_kb: str = ""
    flash_kb: str = ""
    io: str = ""
    die: str = ""
    file: str = ""
    ips: list[dict] = field(default_factory=list)

    def as_dict(self, with_ips: bool = False) -> dict:
        d = {
            "ref_name": self.ref_name,
            "family": self.family,
            "line": self.line,
            "package": self.package,
            "core": self.core,
            "max_freq_mhz": self.freq_mhz,
            "ram_kb": self.ram_kb,
            "flash_kb": self.flash_kb,
            "io_pins": self.io,
            "die": self.die,
        }
        if with_ips:
            d["ips"] = self.ips
        return d


class Catalog:
    def __init__(self, root: Path | str = DEFAULT_ROOT) -> None:
        self.root = Path(root)
        self.db = self.root / "db"
        self._mcus: dict[str, McuInfo] | None = None
        self._boards: list[dict] | None = None
        self._families: list[str] | None = None

    # ------------------------------------------------------------------ MCU
    def _load_mcus(self) -> dict[str, McuInfo]:
        if self._mcus is not None:
            return self._mcus
        out: dict[str, McuInfo] = {}
        mcu_dir = self.db / "mcu"
        if mcu_dir.is_dir():
            for f in mcu_dir.glob("*.xml"):
                if f.name in ("families.xml", "rules.xml", "compatibility.xml"):
                    continue
                try:
                    root = ET.parse(f).getroot()
                except ET.ParseError:
                    continue
                if root.tag.replace(NS, "") != "Mcu":
                    continue
                info = McuInfo(
                    ref_name=root.get("RefName", f.stem),
                    family=root.get("Family", ""),
                    line=root.get("Line", ""),
                    package=root.get("Package", ""),
                    file=f.name,
                )

                def text(tag: str, _root=root) -> str:
                    el = _root.find(NS + tag)
                    return (el.text or "").strip() if el is not None else ""

                info.core = text("Core")
                info.freq_mhz = text("Frequency")
                info.ram_kb = text("Ram")
                info.io = text("IONb")
                info.die = text("Die")
                flashes = [ (e.text or "").strip() for e in root.findall(NS + "Flash") ]
                info.flash_kb = "/".join([x for x in flashes if x])
                for ip in root.findall(NS + "IP"):
                    info.ips.append({
                        "instance": ip.get("InstanceName", ""),
                        "name": ip.get("Name", ""),
                        "version": ip.get("Version", ""),
                        "config_file": ip.get("ConfigFile", ""),
                    })
                out[info.ref_name] = info
        else:
            # no installation: read the bundled projection instead
            out.update(self._load_from_pack())
        self._mcus = out
        return out

    def _pack(self):
        from .bundle import Pack
        if getattr(self, "_pack_obj", None) is None:
            self._pack_obj = Pack()
        return self._pack_obj

    def _load_from_pack(self) -> dict[str, McuInfo]:
        """Project the bundled zip into McuInfo records (standalone mode)."""
        pack = self._pack()
        if not pack.available:
            return {}
        out: dict[str, McuInfo] = {}
        for row in pack.mcus():
            info = McuInfo(
                ref_name=row.get("ref_name", ""),
                family=row.get("family", ""),
                package=row.get("package", ""),
                file=row.get("source", ""),
            )
            info.core = row.get("core") or ""
            info.ram_kb = str(row.get("ram") or "")
            info.flash_kb = str(row.get("flash") or "")
            info.io = str(len(row.get("pins") or []))
            for ip in row.get("ips") or []:
                info.ips.append({"instance": ip.get("instance", ""),
                                 "name": ip.get("name", ""),
                                 "version": ip.get("version", ""),
                                 "config_file": ""})
            if info.ref_name:
                out[info.ref_name] = info
        return out

    def mcus(self) -> list[McuInfo]:
        return list(self._load_mcus().values())

    def get_mcu(self, ref_name: str) -> McuInfo | None:
        mcus = self._load_mcus()
        if ref_name in mcus:
            return mcus[ref_name]
        low = ref_name.lower()
        for k, v in mcus.items():
            if k.lower() == low:
                return v
        return None

    @staticmethod
    def _flat(text: str) -> str:
        return "".join(ch for ch in text.lower() if ch.isalnum())

    @staticmethod
    def _expand_db_name(name: str) -> list[str]:
        """Expand a db RefName's parenthesised ranges into concrete part prefixes.

        'STM32F103C(8-B)Tx'  -> ['stm32f103c8tx', 'stm32f103cbtx']
        'STM32F103C(4-6)Tx'  -> ['stm32f103c4tx', 'stm32f103c6tx']
        'STM32F103R(8-B)Hx'  -> ['stm32f103r8hx', 'stm32f103rbhx']
        'STM32F030F4Px'      -> ['stm32f030f4px']
        """
        out: list[str] = []
        m = re.search(r"\(([^)]*)\)", name)
        if not m:
            out.append(name.lower())
            return out
        inner = m.group(1)
        head = name[:m.start()].lower()
        tail = name[m.end():].lower()
        pieces = inner.split(",")
        for piece in pieces:
            piece = piece.strip()
            parts = [p.strip() for p in piece.split("-")] if piece else []
            if len(parts) > 1:
                variants: list[str] = []
                for j, part in enumerate(parts):
                    if j == 0:
                        variants.append(part.lower())
                        continue
                    prev = variants[-1]
                    if part.isdigit() and prev.isdigit():
                        for code in range(int(prev) + 1, int(part) + 1):
                            variants.append(str(code))
                    elif part.isalpha() and prev.isdigit():
                        # digits(0-9) then A..Z, e.g. '8-B'
                        for ch in "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ":
                            if ch <= prev[-1]:
                                continue
                            variants.append(ch.lower())
                            if ch.lower() == part.lower():
                                break
                    elif part.isalpha() and prev.isalpha():
                        cur = ord(prev.upper())
                        end = ord(part.upper())
                        while cur < end:
                            cur += 1
                            variants.append(chr(cur).lower())
                    else:
                        variants.append(part.lower())
            elif piece:
                variants = [piece.lower()]
            else:
                variants = []
            for v in variants:
                out.append(head + v.lower() + tail)
        return out

    # characters that a real part number appends after the db name: the pin
    # count / temperature code (6, 7) or an option letter (Q, G, Z, Y, I...).
    _PN_SUFFIXES = ("", "q", "g", "y", "z", "i", "t", "u", "x", "6", "7")

    def resolve_mcu(self, query: str) -> list[str]:
        """Map a user part number to the db RefName.

        Tiers, each fully evaluated before the next:
          1. exact RefName
          2. exact expansion of a db range name (STM32F103C8Tx)
          3. db expansion plus a part-number suffix (STM32U575ZIT6Q -> ...ZITxQ)
          4. package-char-insensitive match (STM32F103C8T6 -> STM32F103C(8-B)Tx)
          5. substring over flattened names
        """
        q = query.strip()
        mcus = self._load_mcus()
        for k in mcus:
            if k.lower() == q.lower():
                return [k]
        key = self._flat(q)
        expansions: dict[str, list[str]] = {k: self._expand_db_name(k) for k in mcus}

        for k, variants in expansions.items():
            if key in variants:
                return [k]

        for suffix in self._PN_SUFFIXES[1:]:
            target = key[:-len(suffix)] if key.endswith(suffix) else None
            if not target:
                continue
            for k, variants in expansions.items():
                if target in variants:
                    return [k]

        scored: list[tuple[int, str]] = []
        for k, variants in expansions.items():
            for variant in variants:
                if key[:-1] == variant[:-1]:
                    scored.append((1, k))
                    break
                if variant.startswith(key) or key.startswith(variant[:-2] if variant.endswith("x") else variant):
                    scored.append((3, k))
                    break
        scored.sort(key=lambda x: (x[0], len(x[1])))
        if scored:
            out: list[str] = []
            for _, k in scored:
                if k not in out:
                    out.append(k)
            return out[:25]

        hits = [k for k in mcus if key in self._flat(k)]
        hits.sort(key=len)
        return hits[:25]

    def find_mcu(self, query: str, limit: int = 25) -> list[dict]:
        """Resolve then describe; falls back to substring search."""
        names = self.resolve_mcu(query)
        mcus = self._load_mcus()
        rows = [mcus[n].as_dict() for n in names if n in mcus]
        if rows:
            return rows[:limit]
        q = query.lower()
        hits = [m for m in mcus.values() if q in m.ref_name.lower()]
        hits.sort(key=lambda m: (len(m.ref_name), m.ref_name))
        return [m.as_dict() for m in hits[:limit]]

    def mcus_by_family(self, family: str, limit: int = 200) -> list[dict]:
        fam = family.upper()
        hits = [m for m in self.mcus() if m.family.upper() == fam]
        hits.sort(key=lambda m: m.ref_name)
        return [m.as_dict() for m in hits[:limit]]

    def families(self) -> list[str]:
        if self._families is None:
            self._families = sorted({m.family for m in self.mcus() if m.family})
        return self._families

    # --------------------------------------------------------------- boards
    def boards(self) -> list[dict]:
        if self._boards is not None:
            return self._boards
        rows: list[dict] = []
        bdir = self.db / "plugins" / "boardmanager"
        if bdir.is_dir():
            for pdsc in sorted(bdir.glob("*.pdsc")):
                try:
                    root = ET.parse(pdsc).getroot()
                except ET.ParseError:
                    continue
                # boards may appear as <board ...> or inside <boards><board>
                for el in root.iter():
                    tag = el.tag.split("}")[-1]
                    if tag.lower() != "board":
                        continue
                    name = el.get("name") or el.get("Name") or ""
                    if not name:
                        continue
                    rows.append({
                        "name": name,
                        "mcu": el.get("mcu") or el.get("Mcu") or el.get("McuRefName") or "",
                        "vendor": el.get("vendor") or el.get("Vendor") or "",
                        "source": pdsc.name,
                    })
        # de-duplicate, keep first
        seen = set()
        uniq = []
        for r in rows:
            if r["name"] in seen:
                continue
            seen.add(r["name"])
            uniq.append(r)
        self._boards = uniq
        return uniq

    def find_board(self, query: str, limit: int = 25) -> list[dict]:
        q = query.lower()
        hits = [b for b in self.boards() if q in b["name"].lower()]
        hits.sort(key=lambda b: (len(b["name"]), b["name"]))
        return hits[:limit]

    # ------------------------------------------------------------ resources
    def ip_mode_files(self) -> list[str]:
        d = self.db / "mcu" / "IP"
        return sorted(p.name for p in d.glob("*_Cube_Modes.xml")) if d.is_dir() else []

    def config_files(self) -> list[str]:
        d = self.db / "mcu" / "config"
        return sorted(p.name for p in d.glob("*_Configs.xml")) if d.is_dir() else []

    def templates(self) -> list[str]:
        d = self.db / "templates"
        return sorted(p.name for p in d.glob("*.ftl")) if d.is_dir() else []

    def ip_modes_for(self, mcu_ref: str, instance: str | None = None) -> list[dict]:
        """Return the IP list of an MCU, optionally filtered by instance."""
        info = self.get_mcu(mcu_ref)
        if not info:
            return []
        if instance:
            return [ip for ip in info.ips if ip["instance"].lower() == instance.lower()]
        return info.ips

    def index(self) -> dict:
        mcus = self.mcus()
        fam: dict[str, int] = {}
        for m in mcus:
            fam[m.family] = fam.get(m.family, 0) + 1
        return {
            "mcu_count": len(mcus),
            "board_count": len(self.boards()),
            "families": fam,
            "ip_mode_files": len(self.ip_mode_files()),
            "config_files": len(self.config_files()),
            "templates": len(self.templates()),
            "root": str(self.root),
        }


if __name__ == "__main__":
    import sys

    cat = Catalog()
    if len(sys.argv) == 1 or sys.argv[1] == "index":
        print(json.dumps(cat.index(), indent=1))
    elif sys.argv[1] == "mcu":
        print(json.dumps(cat.find_mcu(sys.argv[2]), indent=1))
    elif sys.argv[1] == "board":
        print(json.dumps(cat.find_board(sys.argv[2]), indent=1))
