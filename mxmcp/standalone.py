"""Standalone project engine: build and validate projects without CubeMX.

Everything here works from the bundled data pack (`mxmcp/data/cubemx-db.zip`):
MCU pin tables with their selectable signals, IP mode/parameter schemas, and the
`.ioc` format. No JVM, no installation.

The model mirrors what CubeMX stores, so a project written here opens in CubeMX
and vice versa:

  Mcu.Name / Mcu.Family / Mcu.Package / Mcu.UserName
  Mcu.Pin0..N      = full pin names  (PC13-TAMPER-RTC, PD0-OSC_IN)
  Mcu.IP0..N       = IP instance names (USART1, RCC, NVIC, SYS…)
  <PIN>.Signal     = bound signal (GPIO_Output, USART1_TX, RCC_OSC_IN…)
  <PIN>.Mode       = peripheral mode that owns the pin
  <PIN>.Locked
  <IP>.IPParameters= registered parameter names
  <IP>.<param>     = parameter values
  NVIC.<IRQ>       = "<priority>,<subpriority>,<enabled>:<ENABLE|DISABLE>,…"
  ProjectManager.* = project/toolchain options

Validation is real: a signal may only be bound to a pin that advertises it in the
MCU xml, and a pin has exactly one signal. Conflicts are reported, not silently
accepted — the same guarantee the CubeMX engine gives.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .bundle import Pack
from .ioc import IocProject


class StandaloneError(RuntimeError):
    """A request cannot be served by the standalone engine."""


# --------------------------------------------------------------------- model
@dataclass
class PinCapability:
    name: str            # full pin name: PC13-TAMPER-RTC
    type: str            # I/O, Power, Reset…
    position: str
    signals: list[str]   # selectable signals as the db declares them
    gpio_modes: list[str] = field(default_factory=list)   # Input,Output,Analog…

    def selectable(self) -> list[str]:
        """Signals CubeMX accepts here.

        The db lists a generic `GPIO` signal carrying `IOModes`
        (Input,Output,Analog,EVENTOUT,EXTI); the CLI/.ioc uses the derived names
        `GPIO_Input`, `GPIO_Output`, `GPIO_ANALOG`, `GPIO_EVENTOUT`, `GPIO_EXTI*`.
        """
        out: list[str] = []
        for sig in self.signals:
            if sig == "GPIO":
                continue
            out.append(sig)
        modes = self.gpio_modes or (["Input", "Output", "Analog"] if
                                    "GPIO" in self.signals else [])
        for m in modes:
            m2 = m.strip()
            if not m2:
                continue
            if m2.upper() == "EXTI":
                out.extend(["GPIO_EXTI0", "GPIO_EXTI1", "GPIO_EXTI2", "GPIO_EXTI3",
                            "GPIO_EXTI4", "GPIO_EXTI5", "GPIO_EXTI6", "GPIO_EXTI7",
                            "GPIO_EXTI8", "GPIO_EXTI9", "GPIO_EXTI10",
                            "GPIO_EXTI11", "GPIO_EXTI12", "GPIO_EXTI13",
                            "GPIO_EXTI14", "GPIO_EXTI15"])
            elif m2.lower() == "analog":
                out.append("GPIO_ANALOG")
            elif m2.lower() == "eventout":
                out.append("GPIO_EVENTOUT")
            else:
                out.append(f"GPIO_{m2}")
        if "GPIO" in self.signals:
            out.append("GPIO")
        return out


@dataclass
class IpInstance:
    instance: str
    name: str
    version: str = ""


@dataclass
class Device:
    ref_name: str
    family: str
    package: str
    core: str = ""
    flash: int | None = None
    ram: int | None = None
    pins: dict[str, PinCapability] = field(default_factory=dict)
    ips: list[IpInstance] = field(default_factory=list)
    source: str = ""

    def signals_for(self, pin: str) -> list[str]:
        """Every signal CubeMX accepts on this pin (GPIO_* expanded)."""
        cap = self.pins.get(pin)
        return cap.selectable() if cap else []

    def pins_for_signal(self, signal: str) -> list[str]:
        return sorted(p for p, cap in self.pins.items() if signal in cap.signals)

    def ip(self, instance: str) -> IpInstance | None:
        for ip in self.ips:
            if ip.instance.lower() == instance.lower():
                return ip
        return None


class DeviceDB:
    """Device lookup over the bundled data pack (or an installation)."""

    def __init__(self, pack: Pack | None = None) -> None:
        self.pack = pack or Pack()
        self._cache: dict[str, Device] = {}
        self._names: list[str] | None = None

    @property
    def available(self) -> bool:
        return self.pack.available

    def names(self) -> list[str]:
        if self._names is None:
            out = []
            for row in self.pack.mcus():
                ref = row.get("ref_name")
                if ref:
                    out.append(ref)
            self._names = sorted(set(out))
        return self._names

    def device(self, ref: str) -> Device:
        if ref in self._cache:
            return self._cache[ref]
        row = self.pack.mcu(ref)
        if row is None:
            raise StandaloneError(f"unknown MCU {ref!r} in the bundled database")
        dev = Device(ref_name=row.get("ref_name", ref),
                     family=row.get("family", ""),
                     package=row.get("package", ""),
                     core=row.get("core") or "",
                     flash=row.get("flash"),
                     ram=row.get("ram"),
                     source=row.get("source", ""))
        for p in row.get("pins") or []:
            dev.pins[p["name"]] = PinCapability(
                name=p["name"], type=p.get("type", ""),
                position=p.get("position", ""),
                signals=list(p.get("signals") or []),
                gpio_modes=list(p.get("gpio_modes") or []))
        for ip in row.get("ips") or []:
            dev.ips.append(IpInstance(ip.get("instance", ""), ip.get("name", ""),
                                      ip.get("version", "")))
        self._cache[ref] = dev
        return dev

    def resolve(self, query: str) -> list[str]:
        """Resolve a marketing part number to db RefNames.

        Reuses `Catalog.resolve_mcu`, which implements the ST part-number rules
        (range names `(8-B)`, package letters, option suffixes) and itself falls
        back to the bundled pack when no installation is present.
        """
        from .catalog import DEFAULT_ROOT, Catalog
        root = DEFAULT_ROOT if (DEFAULT_ROOT / "db" / "mcu").is_dir() else Path(".")
        try:
            hits = Catalog(root).resolve_mcu(query)
            if hits:
                return hits
        except Exception:  # noqa: BLE001 - fall through to the simple tiers
            pass
        q = query.strip()
        names = self.names()
        if q in names:
            return [q]
        low = q.lower()
        exact = [n for n in names if n.lower() == low]
        if exact:
            return exact
        return [n for n in names if low in n.lower()]

    def search(self, query: str, limit: int = 50) -> list[dict]:
        return self.pack.find(query, limit=limit)


# ------------------------------------------------------------------ project
class StandaloneProject:
    """A project held entirely in memory, serialised as `.ioc`."""

    def __init__(self, db: DeviceDB, pid: str = "project") -> None:
        self.db = db
        self.pid = pid
        self.device: Device | None = None
        self.pin_signals: dict[str, str] = {}
        self.pin_meta: dict[str, dict] = {}
        self.ip_params: dict[str, dict[str, str]] = {}
        self.ip_registered: dict[str, list[str]] = {}
        self.nvic: dict[str, dict] = {}
        self.options: dict[str, str] = {}
        self.extra: dict[str, str] = {}

    # ---------------------------------------------------------------- load
    @classmethod
    def create(cls, db: DeviceDB, mcu: str, pid: str = "project",
               toolchain: str = "Makefile") -> StandaloneProject:
        names = db.resolve(mcu)
        if not names:
            raise StandaloneError(f"no MCU matches {mcu!r}")
        ref = names[0]
        dev = db.device(ref)
        p = cls(db, pid)
        p.device = dev
        p.options.update({
            "ProjectManager.ProjectName": pid,
            "ProjectManager.ProjectFileName": f"{pid}.ioc",
            "ProjectManager.TargetToolchain": toolchain,
            "ProjectManager.CoupleFile": "false",
            "ProjectManager.KeepUserCode": "true",
            "ProjectManager.StackSize": "0x400",
            "ProjectManager.HeapSize": "0x200",
            "ProjectManager.LastFirmware": "true",
            "ProjectManager.MainLocation": "Core/Src",
            "ProjectManager.DeviceId": ref,
        })
        p.extra.update({
            "Mcu.Name": ref,
            "Mcu.Family": f"STM32{dev.family}" if dev.family else "",
            "Mcu.Package": dev.package,
            "Mcu.UserName": mcu,
            "Mcu.CPN": "",
            "Mcu.RPN": "",
            "File.Version": "6",
            "KeepUserPlacement": "false",
        })
        # RCC/NVIC/SYS always exist in a CubeMX project
        for inst in ("RCC", "NVIC", "SYS"):
            if dev.ip(inst):
                p.register_ip(inst)
        return p

    @classmethod
    def load(cls, db: DeviceDB, path: Path | str) -> StandaloneProject:
        ioc = IocProject.load(path)
        p = cls(db, Path(path).stem)
        ref = ioc.get("Mcu.Name")
        try:
            p.device = db.device(ref)
        except StandaloneError:
            p.device = None
        for key, value in ioc.entries.items():
            if key.startswith("ProjectManager."):
                p.options[key] = value
            elif key.startswith("Mcu.") and not re.match(
                    r"^Mcu\.(Pin|IP)\d+$", key):
                p.extra[key] = value
            elif re.match(r"^Mcu\.IP\d+$", key):
                p.register_ip(value)
            elif re.match(r"^Mcu\.Pin\d+$", key):
                continue
            elif key.startswith("NVIC."):
                p.nvic[key.split(".", 1)[1]] = _parse_nvic(value)
            elif "." in key:
                head, tail = key.split(".", 1)
                if head in ("RCC", "SYS") or (p.device and p.device.ip(head)):
                    if tail == "IPParameters":
                        p.ip_registered[head] = [x for x in value.split(",") if x]
                    else:
                        p.ip_params.setdefault(head, {})[tail] = value
        # pins
        for key, value in ioc.entries.items():
            head, _, tail = key.partition(".")
            if not tail or head.startswith(("Mcu", "ProjectManager", "NVIC",
                                            "File", "Keep")) or head in p.ip_params:
                continue
            if tail == "Signal":
                p.pin_signals[head] = value
            elif tail in ("Mode", "Locked", "GPIOParameters", "GPIO_Label",
                          "PinAttribute", "Signal", "GPIO_PuPd", "GPIO_Speed",
                          "GPIO_Mode"):
                p.pin_meta.setdefault(head, {})[tail] = value
        return p

    # -------------------------------------------------------------- mutate
    def register_ip(self, instance: str) -> None:
        inst = instance.strip()
        if not inst:
            return
        self.ip_registered.setdefault(inst, [])
        self.ip_params.setdefault(inst, {})

    def ips(self) -> list[str]:
        return sorted(self.ip_registered)

    def available_signals(self, pin: str) -> list[str]:
        if not self.device:
            return []
        return self.device.signals_for(pin)

    def set_pin(self, pin: str, signal: str) -> dict:
        dev = self.require_device()
        full = self._full_pin_name(pin)
        if full is None:
            raise StandaloneError(f"pin {pin!r} does not exist on {dev.ref_name}")
        signals = dev.signals_for(full)
        if signal not in signals:
            close = [s for s in signals if signal.split("_")[0] in s][:8]
            raise StandaloneError(
                f"{signal!r} is not available on {full}. "
                + (f"Did you mean: {', '.join(close)}" if close else
                   f"Available: {', '.join(signals[:12])}"))
        prev_owner = self.pin_signals.get(full)
        for other, sig in list(self.pin_signals.items()):
            if other != full and sig == signal and not signal.startswith("GPIO_"):
                self.pin_signals.pop(other, None)
                self.pin_meta.pop(other, None)
        self.pin_signals[full] = signal
        meta = self.pin_meta.setdefault(full, {})
        meta.setdefault("Locked", "true")
        mode = self._mode_for_signal(signal)
        if mode:
            meta["Mode"] = mode
        if signal.startswith("GPIO_"):
            meta.setdefault("GPIOParameters",
                            "GPIO_Label,GPIO_ModeDefaultOutputPP")
        return {"pin": full, "signal": signal, "previous": prev_owner,
                "mode": mode}

    def reset_pin(self, pin: str) -> dict:
        full = self._full_pin_name(pin)
        old = self.pin_signals.pop(full, None)
        self.pin_meta.pop(full, None)
        return {"pin": full, "was": old}

    def set_mode(self, ip: str, mode: str) -> dict:
        """Enable a peripheral/middleware mode (validated against the db)."""
        dev = self.require_device()
        inst = dev.ip(ip)
        if inst is None:
            known = sorted({i.instance for i in dev.ips})
            raise StandaloneError(
                f"{ip!r} is not present on {dev.ref_name}. "
                f"Instances: {', '.join(known[:20])}")
        modes = self.ip_mode_names(inst.name)
        if modes and mode not in modes and mode not in (
                "Asynchronous", "Synchronous", "Single", "Master", "Slave"):
            raise StandaloneError(
                f"{mode!r} is not a mode of {inst.name}; known: "
                f"{', '.join(modes[:14])}")
        self.register_ip(ip)
        self.ip_params.setdefault(ip, {})["Mode"] = mode
        reg = self.ip_registered.setdefault(ip, [])
        if "Mode" not in reg:
            reg.append("Mode")
        return {"ip": ip, "mode": mode, "registered": reg}

    def set_ip_param(self, ip: str, name: str, value: str) -> dict:
        self.register_ip(ip)
        self.ip_params.setdefault(ip, {})[name] = str(value)
        reg = self.ip_registered.setdefault(ip, [])
        if name not in reg:
            reg.append(name)
        return {"ip": ip, "param": name, "value": str(value),
                "registered": reg}

    def set_nvic(self, irq: str, *, priority: int | str | None = None,
                 subpriority: int | str | None = None,
                 enabled: bool | None = None) -> dict:
        row = self.nvic.setdefault(irq, {"priority": "0", "subpriority": "0",
                                         "enabled": False, "extra": ""})
        if priority is not None:
            row["priority"] = str(priority)
        if subpriority is not None:
            row["subpriority"] = str(subpriority)
        if enabled is not None:
            row["enabled"] = bool(enabled)
        return {"irq": irq, **row}

    def ip_mode_names(self, ip_name: str) -> list[str]:
        from .ipmodes import IPModes
        return IPModes(self.db.pack).modes(ip_name)

    # --------------------------------------------------------------- ioc
    def to_ioc(self) -> IocProject:
        ioc = IocProject(path=None)
        for k, v in self.extra.items():
            ioc.set(k, v)
        # IP list
        for i, inst in enumerate(self.ips()):
            ioc.set(f"Mcu.IP{i}", inst)
        ioc.set("Mcu.IPNb", str(len(self.ips())))
        # pins
        for i, pin in enumerate(sorted(self.pin_signals)):
            ioc.set(f"Mcu.Pin{i}", pin)
        ioc.set("Mcu.PinsNb", str(len(self.pin_signals)))
        for pin, sig in sorted(self.pin_signals.items()):
            ioc.set(f"{pin}.Signal", sig)
            for mk, mv in (self.pin_meta.get(pin) or {}).items():
                if mk == "Signal":
                    continue
                ioc.set(f"{pin}.{mk}", mv)
        # ip parameters
        for inst, params in self.ip_params.items():
            reg = self.ip_registered.get(inst) or list(params)
            if reg:
                ioc.set(f"{inst}.IPParameters", ",".join(reg))
            for name, value in params.items():
                ioc.set(f"{inst}.{name}", value)
        # nvic
        for irq, row in self.nvic.items():
            ioc.set(f"NVIC.{irq}",
                    f"{row['priority']},{row['subpriority']},"
                    f"{'true' if row['enabled'] else 'false'}"
                    f":{'ENABLE' if row['enabled'] else 'DISABLE'},"
                    f"{row['priority']}")
        for k, v in self.options.items():
            ioc.set(k, v)
        return ioc

    def save(self, path: Path | str) -> Path:
        return self.to_ioc().save(path)

    # ---------------------------------------------------------- validate
    def problems(self) -> list[str]:
        out: list[str] = []
        if not self.device:
            return ["Mcu.Name is unknown to the bundled database"]
        for pin, sig in self.pin_signals.items():
            if pin not in self.device.pins:
                out.append(f"{pin}: not present on {self.device.ref_name}")
                continue
            if sig not in self.device.pins[pin].selectable():
                out.append(f"{pin}: {sig} is not selectable on this pin")
        seen: dict[str, str] = {}
        for pin, sig in self.pin_signals.items():
            if sig.startswith("GPIO_"):
                continue
            if sig in seen:
                out.append(f"{sig}: bound to both {seen[sig]} and {pin}")
            seen[sig] = pin
        for inst in self.ip_registered:
            if not self.device.ip(inst):
                out.append(f"{inst}: IP not present on {self.device.ref_name}")
        return out

    # ------------------------------------------------------------ helpers
    def require_device(self) -> Device:
        if not self.device:
            raise StandaloneError("project has no valid MCU")
        return self.device

    def _full_pin_name(self, pin: str) -> str | None:
        dev = self.device
        if not dev:
            return None
        if pin in dev.pins:
            return pin
        base = pin.split("-")[0]
        for name in dev.pins:
            if name == base or name.startswith(base + "-"):
                return name
        return None

    def _mode_for_signal(self, signal: str) -> str:
        if signal.startswith("GPIO_"):
            return ""
        head = signal.split("_")[0]
        return head


def _parse_nvic(value: str) -> dict:
    """"<prio>,<sub>,<enabled>:ENABLE,<prio>" -> dict."""
    main, _, tail = value.partition(":")
    parts = [p.strip() for p in main.split(",")]
    row = {"priority": parts[0] if parts else "0",
           "subpriority": parts[1] if len(parts) > 1 else "0",
           "enabled": (parts[2].lower() == "true") if len(parts) > 2 else False,
           "extra": tail}
    return row
