"""Self-contained data pack: make mxmcp work with no CubeMX installation.

The MCP server only needs the *installation* for two things: launching the JVM
engine (project create/save/generate/clock solve) and reading `db/`. Everything
else — MCU/board search, pin functions, IP mode catalogue, parameter schemas,
`.ioc` read/write, template inventory, RTOS schema, middleware list, CLI registry,
verify — is data driven.

`bundle.py` turns the shipped `db/` into one compact zip so those capabilities
work on a machine that never installed CubeMX:

  python -m mxmcp.bundle build --cubemx-root "C:\\Program Files\\...\\STM32CubeMX"
  python -m mxmcp.bundle info        # what the pack contains
  python -m mxmcp.bundle verify      # integrity check of the pack

Layout inside `mxmcp/data/cubemx-db.zip`:

  mcu/<Family>/<RefName>.json   compact MCU projection (pins, alt functions, IPs)
  families.json                 family tree + counts
  boards.json                   board manager catalogue
  ip_modes.json                 every IP mode + parameter schema (274 IPs)
  templates.json                template inventory (path, bytes, sha256)
  meta.json                     build provenance (source root, db version, counts)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import zipfile
from collections.abc import Iterable
from pathlib import Path

DEFAULT_ROOT = Path(r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX")
HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
PACK = DATA / "cubemx-db.zip"
NS = "{http://mcd.rou.st.com/modules.php?name=mcu}"


# --------------------------------------------------------------------- helpers
def _local(tag: str) -> str:
    return tag.split("}")[-1]


def _attr(el, name: str, default: str = "") -> str:
    return el.get(name, el.get(NS + name, default))


def _iter(root, name: str):
    for el in root.iter():
        if _local(el.tag) == name:
            yield el


def _mcu_projection(path: Path) -> dict | None:
    """One MCU xml -> compact dict (pins with their selectable signals)."""
    import xml.etree.ElementTree as ET

    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return None
    name = _attr(root, "RefName") or path.stem
    row = {
        "ref_name": name,
        "family": _attr(root, "Family"),
        "package": _attr(root, "PackageName") or _attr(root, "Package"),
        "rpn": _attr(root, "RPN"),
        "core": "",
        "flash": None,
        "ram": None,
        "pins": [],
        "ips": [],
        "clock_tree": _attr(root, "ClockTree"),
        "source": path.name,
    }
    for core in _iter(root, "Core"):
        row["core"] = _attr(core, "Name") or (core.text or "").strip()
        break
    for flash in _iter(root, "Flash"):
        try:
            row["flash"] = int(_attr(flash, "Size") or 0) or None
        except ValueError:
            pass
        break
    for ram in _iter(root, "Ram"):
        try:
            row["ram"] = int(_attr(ram, "Size") or 0) or None
        except ValueError:
            pass
        break
    for ip in _iter(root, "IP"):
        row["ips"].append({"name": _attr(ip, "Name"),
                           "instance": _attr(ip, "InstanceName"),
                           "version": _attr(ip, "Version"),
                           "clock": _attr(ip, "ClockEnableMode")})
    for pin in _iter(root, "Pin"):
        entry = {"name": _attr(pin, "Name"), "type": _attr(pin, "Type"),
                 "position": _attr(pin, "Position"),
                 "variant": _attr(pin, "Variant"), "signals": [],
                 "gpio_modes": []}
        for sig in pin:
            if _local(sig.tag) in ("PinSignal", "Signal"):
                nm = _attr(sig, "Name")
                if nm:
                    entry["signals"].append(nm)
                    if nm == "GPIO":
                        # Input,Output,Analog,EVENTOUT,EXTI -> the GPIO_* pseudo
                        # signals CubeMX accepts on the command line
                        entry["gpio_modes"] = [
                            x.strip() for x in _attr(sig, "IOModes").split(",")
                            if x.strip()]
        row["pins"].append(entry)
    return row


def _families(root: Path) -> dict:
    import xml.etree.ElementTree as ET

    out: dict = {"families": [], "counts": {}}
    f = root / "db" / "mcu" / "families.xml"
    if not f.exists():
        return out
    try:
        tree = ET.parse(f).getroot()
    except ET.ParseError:
        return out
    for fam in _iter(tree, "Family"):
        name = _attr(fam, "Name")
        subs = []
        for sub in fam:
            if _local(sub.tag) == "SubFamily":
                subs.append(_attr(sub, "Name"))
        out["families"].append({"name": name, "subfamilies": subs})
    out["counts"] = {"families": len(out["families"]),
                     "subfamilies": sum(len(f["subfamilies"])
                                        for f in out["families"])}
    return out


def _boards(root: Path) -> dict:
    import xml.etree.ElementTree as ET

    out = {"boards": []}
    base = root / "db" / "plugins" / "boardmanager"
    if not base.exists():
        return out
    for pdsc in sorted(base.rglob("*.pdsc")):
        try:
            tree = ET.parse(pdsc).getroot()
        except ET.ParseError:
            continue
        for board in _iter(tree, "board"):
            name = board.get("name") or board.get("vendor")
            out["boards"].append({
                "name": name,
                "vendor": board.get("vendor", ""),
                "mcu": _attr(board, "device") or board.get("mcu", ""),
                "pdsc": pdsc.name,
                "description": (board.get("description") or "")[:200]})
    out["count"] = len(out["boards"])
    return out


def _ip_modes(root: Path) -> dict:
    """Every IP mode + parameter schema (namespace tolerant)."""
    import xml.etree.ElementTree as ET

    base = root / "db" / "mcu" / "IP"
    detail: dict[str, dict] = {}
    if not base.exists():
        return {"modes_by_ip": {}, "detail": {}}
    for path in sorted(base.glob("*_Modes.xml")):
        try:
            r = ET.parse(path).getroot()
        except ET.ParseError:
            continue
        ip = _attr(r, "Name") or path.stem.split("-")[0]
        ver = _attr(r, "Version")
        modes = sorted({_attr(m, "Name") for m in _iter(r, "RefMode")
                        if _attr(m, "Name")})
        params = [{"name": _attr(p, "Name"), "type": _attr(p, "Type"),
                   "default": _attr(p, "DefaultValue"),
                   "group": _attr(p, "Group")}
                  for p in _iter(r, "RefParameter")][:400]
        detail.setdefault(ip, {})[ver or path.stem] = {
            "ip_type": _attr(r, "IPType"), "file": path.name,
            "modes": modes, "parameters": params}
    flat = {k: sorted({m for v in d.values() for m in v["modes"]})
            for k, d in detail.items()}
    return {"modes_by_ip": flat, "detail": detail}


def _templates(root: Path) -> dict:
    out = []
    for base in (root / "db" / "templates", root / "db" / "plugins",
                 root / "db" / "extra_templates"):
        if not base.exists():
            continue
        for p in base.rglob("*.ftl"):
            try:
                data = p.read_bytes()
            except OSError:
                continue
            out.append({"path": str(p.relative_to(root)).replace("\\", "/"),
                        "bytes": len(data),
                        "sha256": hashlib.sha256(data).hexdigest()})
    return {"count": len(out), "templates": out}


def _pack_member(z, name: str, payload: bytes) -> None:
    """Store a member, gzip-wrapping large JSON payloads."""
    import gzip
    if len(payload) > 2_000_000:
        z.writestr(name + ".gz", gzip.compress(payload, compresslevel=9))
    else:
        z.writestr(name, payload)


def build(root: Path, out: Path, with_templates: bool = True) -> int:
    root = Path(root)
    db = root / "db"
    if not db.is_dir():
        raise SystemExit(f"not a CubeMX installation: {root}")
    out.parent.mkdir(parents=True, exist_ok=True)
    mcu_dir = db / "mcu"
    files = sorted(mcu_dir.glob("*.xml"))
    print(f"MCU xml files: {len(files)}", flush=True)
    written = 0
    counts = {"mcu": 0, "pins": 0, "ips": 0}
    tmp = out.with_suffix(".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for path in files:
            row = _mcu_projection(path)
            if not row:
                continue
            fam = re.sub(r"[^\w.-]", "_", row["family"] or "unknown")
            name = re.sub(r"[^\w.()\-]", "_", row["ref_name"] or path.stem)
            z.writestr(f"mcu/{fam}/{name}.json",
                       json.dumps(row, separators=(",", ":")))
            counts["mcu"] += 1
            counts["pins"] += len(row["pins"])
            counts["ips"] += len(row["ips"])
            written += 1
            if written % 250 == 0:
                print(f"  {written}/{len(files)} …", flush=True)
        fams = _families(root)
        z.writestr("families.json", json.dumps(fams))
        boards = _boards(root)
        z.writestr("boards.json", json.dumps(boards))
        modes = _ip_modes(root)
        z.writestr("ip_modes.json", json.dumps(modes))
        if with_templates:
            tpl = _templates(root)
            z.writestr("templates.json", json.dumps(tpl))
        # generator/codegen inputs that live outside db/
        here = Path(__file__).resolve().parent / "data"
        for extra in ("config_slim.json", "middleware.json", "rtos_model.json",
                      "cli_registry.json"):
            src = here / extra
            if src.exists():
                _pack_member(z, extra, src.read_bytes())
        edge = here / "edge_tables.json"
        if edge.exists():
            _pack_member(z, "edge_tables.json", edge.read_bytes())
        meta = {
            "source_root": str(root),
            "db_version": _db_version(root),
            "counts": {**counts, "families": fams["counts"].get("families"),
                       "boards": boards.get("count"),
                       "ip_modes": len(modes["modes_by_ip"])},
            "notes": "compact projection built by mxmcp.bundle; no ST binaries",
        }
        z.writestr("meta.json", json.dumps(meta, indent=1))
    tmp.replace(out)
    size = out.stat().st_size
    print(f"wrote {out} ({size/1e6:.1f} MB) mcus={counts['mcu']} "
          f"pins={counts['pins']} ips={counts['ips']}")
    return 0


def _db_version(root: Path) -> str:
    for candidate in (root / ".installationinformation", root / "db" / "version.txt"):
        if candidate.is_file():
            try:
                text = candidate.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            m = re.search(r"DB[.\w]*\d", text)
            if m:
                return m.group(0)
    return ""


# ----------------------------------------------------------------- runtime API
class Pack:
    """Read access to the bundled database (works with no installation)."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path or pack_path())
        self._zip: zipfile.ZipFile | None = None

    @property
    def available(self) -> bool:
        return self.path.exists()

    def _open(self) -> zipfile.ZipFile:
        if self._zip is None:
            if not self.path.exists():
                raise FileNotFoundError(
                    f"data pack not found: {self.path}\n"
                    "build it once on a machine that has CubeMX:\n"
                    "  python -m mxmcp.bundle build --cubemx-root "
                    "\"C:\\Program Files\\STMicroelectronics\\STM32Cube\\STM32CubeMX\"")
            self._zip = zipfile.ZipFile(self.path)
        return self._zip

    def meta(self) -> dict:
        return json.loads(self._open().read("meta.json"))

    def names(self, prefix: str = "") -> list[str]:
        return [n for n in self._open().namelist() if n.startswith(prefix)]

    def read(self, member: str) -> bytes:
        z = self._open()
        names = z.namelist()
        if member not in names and member + ".gz" in names:
            import gzip
            return gzip.decompress(z.read(member + ".gz"))
        return z.read(member)

    def json(self, member: str):
        return json.loads(self.read(member))

    def has(self, member: str) -> bool:
        names = self._open().namelist()
        return member in names or member + ".gz" in names

    def mcu(self, ref_name: str) -> dict | None:
        safe = re.sub(r"[^\w.()\-]", "_", ref_name)
        for member in self.names("mcu/"):
            if member.endswith(f"/{safe}.json"):
                return self.json(member)
        return None

    def mcus(self) -> Iterable[dict]:
        for member in self.names("mcu/"):
            if member.endswith(".json"):
                yield self.json(member)

    def find(self, query: str, limit: int = 50) -> list[dict]:
        """Search by db name, family/package, or marketing part number.

        `STM32F103C8T6` must find `STM32F103C(8-B)Tx`, so each row is also matched
        against its expanded part-number aliases.
        """
        q = query.lower().strip()
        if not q:
            return []
        out: list[dict] = []
        for row in self.mcus():
            hay = " ".join(str(row.get(k, "")) for k in
                           ("ref_name", "family", "package", "rpn")).lower()
            if q in hay or any(q.startswith(a[: len(q)]) and len(q) >= 7
                               for a in _aliases(row.get("ref_name", ""))):
                out.append(row)
                if len(out) >= limit:
                    break
        return out


def pack_path() -> Path:
    env = os.environ.get("MXMCP_DATA_PACK")
    return Path(env) if env else PACK


def _aliases(ref_name: str) -> list[str]:
    """Marketing-name aliases of a db RefName, e.g. STM32F103C(8-B)Tx ->
    stm32f103c8tx / stm32f103cbtx (delegated to the catalog expander)."""
    if not ref_name:
        return []
    try:
        from .catalog import Catalog
        return Catalog._expand_db_name(ref_name)
    except Exception:  # noqa: BLE001
        return [ref_name.lower()]


# ------------------------------------------------------------------------ CLI
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m mxmcp.bundle",
                                 description="Build/verify the standalone data pack")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="build the pack from an installation")
    b.add_argument("--cubemx-root", default=str(DEFAULT_ROOT))
    b.add_argument("--out", default=str(PACK))
    b.add_argument("--no-templates", action="store_true")
    sub.add_parser("info", help="show pack contents")
    sub.add_parser("verify", help="check pack integrity")
    ns = ap.parse_args(argv)
    if ns.cmd == "build":
        return build(Path(ns.cubemx_root), Path(ns.out),
                     with_templates=not ns.no_templates)
    pack = Pack()
    if not pack.available:
        print(f"no pack at {pack.path}")
        return 2
    if ns.cmd == "info":
        meta = pack.meta()
        print(json.dumps(meta, indent=1))
        print(f"members: {len(pack.names())}, "
              f"size: {pack.path.stat().st_size/1e6:.1f} MB")
        return 0
    # verify
    bad = 0
    for member in pack.names():
        try:
            pack.read(member)
        except Exception as exc:  # noqa: BLE001
            bad += 1
            print("BAD", member, exc)
    meta = pack.meta()
    print(f"members ok: {len(pack.names()) - bad}/{len(pack.names())}, "
          f"mcus: {meta['counts'].get('mcu')}")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
