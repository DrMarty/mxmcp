"""IP mode and parameter schemas from the bundled pack.

`db/mcu/IP/<IP>*_Modes.xml` declares, per IP version:
  * the modes a user can enable (`RefMode`/`Mode`)
  * every parameter with its type, default and group (`RefParameter`)
  * the value domains (`PossibleValue`) and the conditions that gate them

The standalone engine uses this to validate `set mode` and to offer defaults for
`set ip parameters`, without CubeMX being installed.
"""
from __future__ import annotations

import json
from pathlib import Path

from .bundle import Pack

DATA = Path(__file__).resolve().parent / "data"


class IPModes:
    def __init__(self, pack: Pack | None = None) -> None:
        self.pack = pack or Pack()
        self._data: dict | None = None

    def _load(self) -> dict:
        if self._data is None:
            # packed copy wins, then the shipped snapshot from the analysis pass
            if self.pack.available:
                self._data = self.pack.json("ip_modes.json")
            else:
                snap = DATA / "ip_modes.json"
                if not snap.exists():
                    raise FileNotFoundError(
                        "no IP mode data: build the pack with "
                        "`python -m mxmcp.bundle build`")
                self._data = json.loads(snap.read_text(encoding="utf-8"))
        return self._data

    # ------------------------------------------------------------------ API
    def ips(self) -> list[str]:
        return sorted(self._load()["modes_by_ip"])

    def modes(self, ip: str) -> list[str]:
        data = self._load()["modes_by_ip"]
        if ip in data:
            return list(data[ip])
        for key in data:
            if key.lower() == ip.lower():
                return list(data[key])
        return []

    def has_ip(self, ip: str) -> bool:
        return ip in self._load()["modes_by_ip"]

    def versions(self, ip: str) -> list[str]:
        detail = self._load()["detail"]
        return sorted(detail.get(ip, {}))

    def detail(self, ip: str) -> dict:
        detail = self._load()["detail"]
        if ip in detail:
            return detail[ip]
        for key in detail:
            if key.lower() == ip.lower():
                return detail[key]
        return {}

    def parameters(self, ip: str) -> list[dict]:
        """Parameter schema (name/type/default/group) of an IP."""
        out = []
        seen = set()
        for version, info in self.detail(ip).items():
            for p in info.get("parameters") or []:
                key = (p.get("name"), p.get("type"))
                if key in seen:
                    continue
                seen.add(key)
                out.append({**p, "version": version,
                            "ip_type": info.get("ip_type", "")})
        return out

    def defaults(self, ip: str) -> dict[str, str]:
        return {p["name"]: (p.get("default") or "")
                for p in self.parameters(ip) if p.get("name")}

    def ip_type(self, ip: str) -> str:
        for info in self.detail(ip).values():
            if info.get("ip_type"):
                return info["ip_type"]
        return ""

    def summary(self) -> dict:
        data = self._load()
        kinds: dict[str, int] = {}
        for versions in data["detail"].values():
            for info in versions.values():
                k = info.get("ip_type") or "?"
                kinds[k] = kinds.get(k, 0) + 1
        return {"ips": len(data["modes_by_ip"]), "by_type": kinds}
