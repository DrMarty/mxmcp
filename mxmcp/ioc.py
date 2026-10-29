""".ioc project file reader / writer.

The .ioc file is the single source of truth for a CubeMX project. Format observed
in 6.15.0:

  * INI-like `key=value`, one pair per line, ISO-8859-1 with `\\:` escaping for
    colons inside values (e.g. `NVIC.SysTick_IRQn=true\\:15\\:0\\:...`)
  * first line: `#MicroXplorer Configuration settings - do not modify`
  * `Mcu.Pin0..N` lists pin names, `Mcu.IP0..N` lists active IP instances
  * each pin: `<Pin>.Signal`, `<Pin>.Mode`, `<Pin>.Locked`, `<Pin>.GPIO_Label`
  * each IP: `<IP>.IPParameters=<comma list>` then one `<IP>.<Param>=<value>`
  * `ProjectManager.*` holds toolchain / fw package / heap / stack settings

This module keeps unknown keys verbatim so a read->write round trip is lossless,
and offers typed accessors for the structures the MCP tools expose.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

HEADER = "#MicroXplorer Configuration settings - do not modify"
_ESCAPED_COLON = "\u0000COLON\u0000"


def _escape(value: str) -> str:
    return value.replace(":", "\\:")


def _unescape(value: str) -> str:
    return value.replace("\\:", ":")


@dataclass
class IocProject:
    path: Path | None = None
    entries: dict[str, str] = field(default_factory=dict)
    order: list[str] = field(default_factory=list)

    # ------------------------------------------------------------- io
    @classmethod
    def load(cls, path: Path | str) -> IocProject:
        p = Path(path)
        proj = cls(path=p)
        text = p.read_text(encoding="iso-8859-1", errors="replace")
        for raw in text.splitlines():
            line = raw.rstrip("\r")
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            if not k:
                continue
            proj.entries[k] = v
            proj.order.append(k)
        return proj

    def dumps(self) -> str:
        out = [HEADER]
        for k in self.order:
            out.append(f"{k}={self.entries.get(k, '')}")
        for k, v in self.entries.items():
            if k not in self.order:
                out.append(f"{k}={v}")
        return "\n".join(out) + "\n"

    def save(self, path: Path | str | None = None) -> Path:
        p = Path(path or self.path or "project.ioc")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.dumps(), encoding="iso-8859-1", errors="replace")
        self.path = p
        return p

    # --------------------------------------------------------- generic
    def get(self, key: str, default: str = "") -> str:
        return self.entries.get(key, default)

    def set(self, key: str, value: str) -> None:
        if key not in self.entries:
            self.order.append(key)
        self.entries[key] = value

    def drop(self, key: str) -> None:
        self.entries.pop(key, None)
        if key in self.order:
            self.order.remove(key)

    def keys(self, prefix: str) -> list[str]:
        return [k for k in self.order if k.startswith(prefix)]

    def merged(self, ext_path: Path | str | None) -> IocProject:
        """A read-only view with `project_ext.ioc` values layered underneath.

        CubeMX writes defaults (including whole IP tables such as FREERTOS
        objects) only to the extended file; `*.Ext` keys map back to their base
        key so a caller sees one coherent configuration.
        """
        ext_path = Path(ext_path) if ext_path else None
        if not ext_path or not ext_path.exists():
            return self
        ext = IocProject.load(ext_path)
        out = IocProject(path=self.path)
        out.entries = dict(self.entries)
        out.order = list(self.order)
        for key, value in ext.entries.items():
            if key in out.entries:
                continue
            base = key[:-4] if key.endswith(".Ext") else key
            if base in out.entries:
                continue
            if base not in out.entries:
                out.order.append(base)
            out.entries[base] = value
        return out

    # ------------------------------------------------------------ mcu
    @property
    def mcu_name(self) -> str:
        return self.get("Mcu.Name")

    @property
    def mcu_user_name(self) -> str:
        return self.get("Mcu.UserName")

    @property
    def mcu_package(self) -> str:
        return self.get("Mcu.Package")

    @property
    def mcu_cpn(self) -> str:
        return self.get("Mcu.CPN")

    @property
    def family(self) -> str:
        return self.get("Mcu.Family")

    @property
    def cube_version(self) -> str:
        return self.get("MxCube.Version")

    @property
    def db_version(self) -> str:
        return self.get("MxDb.Version")

    # ----------------------------------------------------------- lists
    @staticmethod
    def _numbered(entries: dict[str, str], prefix: str) -> list[str]:
        idx = []
        for k in entries:
            m = re.fullmatch(re.escape(prefix) + r"(\d+)", k)
            if m:
                idx.append((int(m.group(1)), entries[k]))
        idx.sort()
        return [v for _, v in idx]

    @property
    def pins(self) -> list[str]:
        return self._numbered(self.entries, "Mcu.Pin")

    @property
    def ips(self) -> list[str]:
        return self._numbered(self.entries, "Mcu.IP")

    @property
    def third_parties(self) -> list[str]:
        return self._numbered(self.entries, "Mcu.ThirdParty")

    def add_pin(self, pin: str) -> None:
        pins = self.pins
        if pin in pins:
            return
        pins.append(pin)
        self._rewrite_numbered("Mcu.Pin", pins)

    def remove_pin(self, pin: str) -> None:
        pins = [p for p in self.pins if p != pin]
        self._rewrite_numbered("Mcu.Pin", pins)
        for k in self.keys(pin + "."):
            self.drop(k)

    def add_ip(self, instance: str) -> None:
        ips = self.ips
        if instance in ips:
            return
        ips.append(instance)
        self._rewrite_numbered("Mcu.IP", ips)

    def _rewrite_numbered(self, prefix: str, values: list[str]) -> None:
        for k in [k for k in self.order if re.fullmatch(re.escape(prefix) + r"\d+", k)]:
            self.drop(k)
        for i, v in enumerate(values):
            self.set(f"{prefix}{i}", v)
        self.set(f"{prefix}Nb", str(len(values)))

    # -------------------------------------------------------- ip params
    def ip_parameters(self, instance: str) -> list[str]:
        raw = self.get(f"{instance}.IPParameters")
        return [x for x in raw.split(",") if x]

    def get_ip_param(self, instance: str, name: str, default: str = "") -> str:
        return _unescape(self.get(f"{instance}.{name}", default))

    def set_ip_param(self, instance: str, name: str, value: str) -> None:
        self.set(f"{instance}.{name}", _escape(value))
        params = self.ip_parameters(instance)
        if name not in params:
            params.append(name)
            self.set(f"{instance}.IPParameters", ",".join(params))

    def drop_ip_param(self, instance: str, name: str) -> None:
        self.drop(f"{instance}.{name}")
        params = [p for p in self.ip_parameters(instance) if p != name]
        self.set(f"{instance}.IPParameters", ",".join(params))

    # ------------------------------------------------------------ pins
    @dataclass
    class PinState:
        name: str
        signal: str = ""
        mode: str = ""
        label: str = ""
        locked: bool = False
        params: dict = field(default_factory=dict)

    def pin_state(self, pin: str) -> IocProject.PinState:
        st = IocProject.PinState(name=pin)
        st.signal = self.get(f"{pin}.Signal")
        st.mode = self.get(f"{pin}.Mode")
        st.label = _unescape(self.get(f"{pin}.GPIO_Label"))
        st.locked = self.get(f"{pin}.Locked", "false").lower() == "true"
        for k in self.keys(pin + "."):
            st.params[k.split(".", 1)[1]] = _unescape(self.entries[k])
        return st

    def pin_map(self) -> dict[str, dict]:
        return {p: self.pin_state(p).__dict__ for p in self.pins}

    # --------------------------------------------------- project manager
    def project_option(self, name: str, default: str = "") -> str:
        return _unescape(self.get(f"ProjectManager.{name}", default))

    def set_project_option(self, name: str, value: str) -> None:
        self.set(f"ProjectManager.{name}", _escape(value))

    def summary(self) -> dict:
        return {
            "path": str(self.path) if self.path else None,
            "mcu": self.mcu_name,
            "mcu_user_name": self.mcu_user_name,
            "package": self.mcu_package,
            "cpn": self.mcu_cpn,
            "family": self.family,
            "cube_version": self.cube_version,
            "db_version": self.db_version,
            "pins": len(self.pins),
            "ips": self.ips,
            "third_parties": self.third_parties,
            "project": {
                k.split(".", 1)[1]: _unescape(v)
                for k, v in self.entries.items()
                if k.startswith("ProjectManager.")
            },
        }


def diff(a: IocProject, b: IocProject) -> dict:
    """Structural diff between two projects."""
    added, removed, changed = {}, {}, {}
    for k, v in b.entries.items():
        if k not in a.entries:
            added[k] = v
        elif a.entries[k] != v:
            changed[k] = {"from": a.entries[k], "to": v}
    for k, v in a.entries.items():
        if k not in b.entries:
            removed[k] = v
    return {"added": added, "removed": removed, "changed": changed}


if __name__ == "__main__":
    import json
    import sys

    p = IocProject.load(sys.argv[1])
    print(json.dumps(p.summary(), indent=1))
