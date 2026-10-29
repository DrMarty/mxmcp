"""Pin / GPIO / peripheral-mode tools (engine-backed)."""
from __future__ import annotations

import re
from pathlib import Path

from . import schema as S
from .rpc import ToolError
from .store import ProjectManager

# CubeMX prints some lists twice on one line (e.g. "PA9: XPA9: X") and appends an
# empty line; these helpers turn the raw text into clean structures.


def _lines(text: str) -> list[str]:
    return [l for l in text.splitlines() if l.strip()]


def _dedupe_suffix(sig: str) -> str:
    """Normalise a CubeMX list payload.

    The engine prints some replies twice and glues the copies together:
      "GPIO_Output" + "GPIO_Output"                      -> "GPIO_Output"
      "USART1: Asynchronous," + "USART1: Asynchronous,"  -> "USART1: Asynchronous"
      "PC13: X" + "PC13: X"                              -> "PC13: X"
    Strategy: if the string is two identical copies of its first half, drop the
    second half; then collapse a comma list that repeats itself.
    """
    sig = sig.strip().rstrip(",").strip()
    n = len(sig)
    if n >= 6 and n % 2 == 0 and sig[: n // 2] == sig[n // 2:]:
        sig = sig[: n // 2].rstrip(",").strip()
    parts = [p.strip() for p in sig.split(",") if p.strip()]
    # "pin: a, pin: b" -> strip the repeated "pin:" label from every item
    if len(parts) > 1:
        labels = {p.split(":", 1)[0].strip() for p in parts if ":" in p}
        if len(labels) == 1:
            parts = [p.split(":", 1)[1].strip() for p in parts if ":" in p]
    if len(parts) > 1 and len(set(parts)) == 1:
        parts = [parts[0]]
    # a bare "pin: value" pair reduces to the value
    if len(parts) == 1 and parts[0].count(":") == 1:
        parts = [parts[0].split(":", 1)[1].strip()]
    # whole list printed twice: "a, b, a, b" -> "a, b"
    k = len(parts)
    if k and k % 2 == 0 and parts[: k // 2] == parts[k // 2:]:
        parts = parts[: k // 2]
    return ", ".join(parts)


def parse_pinout(text: str) -> list[dict]:
    out = []
    for line in _lines(text):
        if ":" not in line:
            continue
        pin, sig = line.split(":", 1)
        out.append({"pin": pin.strip(), "signal": _dedupe_suffix(sig)})
    return out


def parse_functions(text: str) -> dict:
    lines = _lines(text)
    if not lines:
        return {"pin": "", "functions": []}
    head = lines[0].strip()
    funcs = [l.strip() for l in lines[1:]]
    return {"pin": head, "functions": funcs}


def parse_modes(text: str) -> dict:
    out = {}
    for line in _lines(text):
        if ":" not in line:
            continue
        name, rest = line.split(":", 1)
        rest = rest.strip()
        if rest.lower().startswith("no modes set"):
            out[name.strip()] = []
            continue
        parts = [p.strip() for p in _dedupe_suffix(rest).split(",") if p.strip()]
        out[name.strip()] = parts
    return out


def parse_mapped(text: str) -> dict:
    return parse_modes(text)


def register(server, pm: ProjectManager) -> None:
    def _p(args) -> ProjectManager:
        return pm.get(args["project_id"])

    def _full_pin_name(pm_, project, name: str) -> str:
        """Resolve PC13 -> PC13-TAMPER-RTC using the live pinout table."""
        pinout = parse_pinout(pm_.run(project, "get pinout")["output"])
        names = [x["pin"] for x in pinout]
        if name in names:
            return name
        for cand in names:
            if cand.split("-")[0] == name:
                return cand
        for cand in names:
            if name.lower() in cand.lower():
                return cand
        return name

    # ------------------------------------------------------------- pinout
    def pinout_get(args: dict):
        p = _p(args)
        r = pm.run(p, "get pinout")
        if r["status"] != "OK":
            raise ToolError(r["output"][:300])
        pins = parse_pinout(r["output"])
        if args.get("only_configured"):
            pins = [x for x in pins if x["signal"] and x["signal"].lower()
                    not in ("reset_state", "power")]
        out = {"project_id": p.pid, "count": len(pins), "pins": pins}
        if args.get("sync_ioc"):
            out["ioc_pins"] = len(p.ioc().pins) if p.ioc_path.exists() else 0
        return out

    server.tool(
        "pinout_get",
        "Read the live pinout (`get pinout`): every pin with its current signal. "
        "Filter with only_configured to drop Reset_State/Power pins.",
        S.obj({"project_id": S.s("Project id"),
               "only_configured": S.b("Only pins that carry a signal", True),
               "sync_ioc": S.b("Also report the saved .ioc pin count", False)},
              ["project_id"]), pinout_get)

    def pin_functions(args: dict):
        p = _p(args)
        r = pm.run(p, f"get functions {args['pin']}")
        if r["status"] != "OK":
            raise ToolError(f"pin {args['pin']!r} not found")
        return parse_functions(r["output"])

    server.tool(
        "pin_functions",
        "List every selectable function of a pin (`get functions <pin>`), e.g. "
        "PA9 -> TIM1_CH2, USART1_TX, GPIO_Output ...",
        S.obj({"project_id": S.s("Project id"), "pin": S.s("Pin name, e.g. PA9")},
              ["project_id", "pin"]), pin_functions)

    def pin_set(args: dict):
        p = _p(args)
        # `set pin` wants the MCU pin name from `get pinout` (PC13-TAMPER-RTC),
        # not the short package name (PC13).
        pin = _full_pin_name(pm, p, args["pin"])
        cmds = []
        for sig in args.get("signals", []) or []:
            cmds.append(f'set pin "{pin}" "{sig}"')
        if args.get("signal"):
            cmds.append(f'set pin "{pin}" "{args["signal"]}"')
        if not cmds:
            raise ToolError("provide signal or signals")
        res = pm.run_many(p, cmds)
        ok = all(r["status"] == "OK" for r in res)
        if not ok:
            raise ToolError(f"set pin rejected: {res[-1]['output'][:300] or res[-1]['status']}")
        live = pm.run(p, f"get signal {pin}")
        return {"project_id": p.pid, "pin": pin, "requested": args["pin"],
                "signal": live["output"].strip(), "commands": cmds}

    server.tool(
        "pin_set",
        "Assign a peripheral signal to a pin (`set pin <pin> <signal>`). Signals "
        "must exist in pin_functions; GPIO_Input/GPIO_Output/GPIO_Analog/GPIO_EXTIn "
        "are always valid for GPIO pins.",
        S.obj({"project_id": S.s("Project id"), "pin": S.s("Pin name"),
               "signal": S.s("Signal, e.g. USART1_TX"),
               "signals": S.arr("Apply several signals to the same pin in order",
                                S.s("signal"))},
              ["project_id", "pin"]), pin_set)

    def pin_reset(args: dict):
        p = _p(args)
        target = args.get("pin", ".*")
        pinout = parse_pinout(pm.run(p, "get pinout")["output"])
        hit = [x["pin"] for x in pinout if re.fullmatch(target, x["pin"])]
        if not hit:
            raise ToolError(f"no pin matches {target!r}")
        res = pm.run_many(p, [f'reset pin "{x}"' for x in hit])
        return {"project_id": p.pid, "reset": hit,
                "status": [r["status"] for r in res]}

    server.tool(
        "pin_reset",
        "Free one pin (exact name) or every pin matching a regex (`reset pin`). "
        "Use after pin_set to undo a misassignment.",
        S.obj({"project_id": S.s("Project id"),
               "pin": S.s("Pin name or regex", ".*")},
              ["project_id"]), pin_reset)

    def pin_clear_all(args: dict):
        p = _p(args)
        r = pm.run(p, "clearpinout")
        out = pm.save(p) if args.get("save", True) else {}
        return {"project_id": p.pid, "status": r["status"], **(out or {})}

    server.tool(
        "pin_clear_all",
        "Remove every pin mapping (`clearpinout`), then optionally re-save the .ioc.",
        S.obj({"project_id": S.s("Project id"),
               "save": S.b("Persist the cleared pinout immediately", True)},
              ["project_id"]), pin_clear_all)

    def pin_lock(args: dict):
        p = _p(args)
        val = "true" if args.get("locked", True) else "false"
        r = pm.run(p, f'lock pin "{args["pin"]}" {val}')
        if r["status"] != "OK":
            raise ToolError(r["output"][:200] or "lock pin failed")
        return {"project_id": p.pid, "pin": args["pin"], "locked": val == "true"}

    server.tool(
        "pin_lock",
        "Lock or unlock a pin so generation keeps (or may change) its mapping "
        "(`lock pin <pin> <locked>`).",
        S.obj({"project_id": S.s("Project id"), "pin": S.s("Pin name"),
               "locked": S.b("true to lock", True)},
              ["project_id", "pin"]), pin_lock)

    def pin_reserve(args: dict):
        p = _p(args)
        r = pm.run(p, f'set pinreservation "{args["pin"]}"')
        return {"project_id": p.pid, "pin": args["pin"], "status": r["status"],
                "output": r["output"][:200]}

    server.tool(
        "pin_reserve",
        "Reserve a pin (marks it used without assigning a peripheral) via "
        "`set pinreservation`.",
        S.obj({"project_id": S.s("Project id"), "pin": S.s("Pin name")},
              ["project_id", "pin"]), pin_reserve)

    # --------------------------------------------------------------- modes
    def mode_list(args: dict):
        p = _p(args)
        pat = args.get("peripheral", ".*")
        which = args.get("which", "mapped")
        cmd = {"available": f"get available modes {pat}",
               "all": f"get modes {pat}",
               "mapped": f"get mapped modes {pat}"}[which]
        r = pm.run(p, cmd)
        if r["status"] == "OK":
            return {"project_id": p.pid, "which": which,
                    "modes": parse_modes(r["output"]), "source": "engine"}
        # middleware IPs answer KO until they are integrated, but the shipped
        # db/mcu/IP/*_Modes.xml always knows the legal mode names.
        offline = _offline_modes(pat)
        if offline is not None:
            return {"project_id": p.pid, "which": which, "modes": offline,
                    "source": "db", "engine_reply": r["output"][:180],
                    "note": "middleware IP: modes come from db/mcu/IP/*_Modes.xml"}
        raise ToolError(r["output"][:300])

    server.tool(
        "mode_list",
        "Peripheral modes: `available` (what the MCU can do), `all` (every leaf "
        "mode) or `mapped` (what is currently enabled).",
        S.obj({"project_id": S.s("Project id"),
               "peripheral": S.s("Peripheral regex (USART.* , .*)", ".*"),
               "which": S.s("Selection", ["mapped", "available", "all"], "mapped")},
              ["project_id"]), mode_list)

    def _offline_modes(pattern: str) -> list[str] | None:
        """Mode names for an IP from the shipped db (no engine needed)."""
        import json
        import re as _re
        data = Path(__file__).resolve().parent / "data" / "ip_modes.json"
        if not data.exists():
            return None
        table = json.loads(data.read_text(encoding="utf-8"))["modes_by_ip"]
        try:
            rx = _re.compile(pattern)
        except _re.error:
            rx = None
        out: list[str] = []
        for ip, modes in table.items():
            if ip == pattern or (rx and rx.fullmatch(ip)):
                out.extend(m for m in modes if m not in out)
        return out or None

    def mode_catalog(args: dict):
        import json
        data = Path(__file__).resolve().parent / "data" / "ip_modes.json"
        if not data.exists():
            raise ToolError("mode catalogue missing; run tools/ip_modes_index.py")
        blob = json.loads(data.read_text(encoding="utf-8"))
        detail = blob["detail"]
        name = args.get("ip")
        if name:
            if name not in detail:
                hits = [k for k in detail if name.lower() in k.lower()]
                if not hits:
                    raise ToolError(f"unknown IP {name!r}; {len(detail)} indexed")
                name = hits[0]
            versions = detail[name]
            return {"ip": name, "versions": {
                v: {"ip_type": d["ip_type"], "file": d["file"],
                    "modes": d["modes"], "mode_details": d["mode_details"],
                    "parameter_count": len(d["parameters"])}
                for v, d in versions.items()}}
        rows = []
        for ip, versions in sorted(detail.items()):
            kinds = sorted({d["ip_type"] for d in versions.values()})
            modes = sorted({m for d in versions.values() for m in d["modes"]})
            if args.get("kind") and args["kind"] not in kinds:
                continue
            rows.append({"ip": ip, "kinds": kinds, "mode_count": len(modes),
                         "modes": modes[:14]})
        return {"total": len(rows), "ips": rows}

    server.tool(
        "mode_catalog",
        "Offline catalogue of every IP mode in the shipped database (274 IPs: "
        "peripheral/service/middleware/LPBAM), with per-version mode lists, "
        "parameter counts and the IP type. Works without starting the engine.",
        S.obj({"ip": S.s("Exact IP name (FREERTOS, FATFS, USB_DEVICE…)"),
               "kind": S.s("Filter by ip_type: peripheral/service/middleware/LPBAM")}),
        mode_catalog)

    def mode_set(args: dict):
        p = _p(args)
        ip = args["peripheral"]
        mode = args["mode"]
        # Middleware IPs (FREERTOS, FATFS, USB_HOST…) reject the quoted form that
        # peripheral IPs need, so try the documented form first and fall back.
        attempts = [f'set mode "{ip}" "{mode}"', f"set mode {ip} {mode}"]
        last = None
        for cmd in attempts:
            r = pm.run(p, cmd)
            last = r
            if r["status"] == "OK":
                break
        if last is None or last["status"] != "OK":
            raise ToolError(f"set mode rejected for {ip}/{mode}: "
                            f"{(last or {}).get('output', '')[:300]}")
        active = pm.run(p, f"get mode active {ip}")
        # CubeMX only materialises middleware tables (FREERTOS objects, config
        # defaults…) on save, and those live in project_ext.ioc, so persist now.
        pm.save(p)
        return {"project_id": p.pid, "peripheral": ip, "mode": mode,
                "command": last["command"],
                "active": active["output"].strip(),
                "log": (last.get("log") or "").strip()[:300]}

    server.tool(
        "mode_set",
        "Enable a peripheral mode (`set mode <IP> <mode>`), e.g. USART1 "
        "Asynchronous, RCC Crystal/Ceramic Resonator, TIM3 PWM Generation CH1.",
        S.obj({"project_id": S.s("Project id"), "peripheral": S.s("IP instance"),
               "mode": S.s("Mode name from mode_list")},
              ["project_id", "peripheral", "mode"]), mode_set)

    def mode_reset(args: dict):
        p = _p(args)
        r = pm.run(p, f'reset mode "{args["peripheral"]}" "{args["mode"]}"')
        if r["status"] != "OK":
            raise ToolError(r["output"][:300] or "reset mode failed")
        return {"project_id": p.pid, "peripheral": args["peripheral"],
                "mode": args["mode"], "reset": True}

    server.tool(
        "mode_reset",
        "Disable one mode of a peripheral (`reset mode`).",
        S.obj({"project_id": S.s("Project id"), "peripheral": S.s("IP instance"),
               "mode": S.s("Mode name")},
              ["project_id", "peripheral", "mode"]), mode_reset)

    def mode_check(args: dict):
        p = _p(args)
        r = pm.run(p, f'check mode enabled "{args["peripheral"]}" "{args["mode"]}"')
        text = r["output"].strip()
        return {"project_id": p.pid, "peripheral": args["peripheral"],
                "mode": args["mode"], "output": text,
                "enabled": "is true" in text}

    server.tool(
        "mode_check",
        "Ask CubeMX whether a mode is currently enabled (`check mode enabled`).",
        S.obj({"project_id": S.s("Project id"), "peripheral": S.s("IP instance"),
               "mode": S.s("Mode name")},
              ["project_id", "peripheral", "mode"]), mode_check)

    def sub_modes(args: dict):
        p = _p(args)
        r = pm.run(p, f'get sub-modes "{args["peripheral"]}"')
        return {"project_id": p.pid, "peripheral": args["peripheral"],
                "raw": r["output"].strip()}

    server.tool(
        "sub_modes",
        "Raw sub-mode state dump for one peripheral (`get sub-modes`), useful for "
        "compound modes such as SYS/NVIC.",
        S.obj({"project_id": S.s("Project id"), "peripheral": S.s("IP instance")},
              ["project_id", "peripheral"]), sub_modes)

    def peripheral_list(args: dict):
        p = _p(args)
        r = pm.run(p, "get mcu peripherals")
        rows = []
        for line in _lines(r["output"]):
            parts = line.split()
            if len(parts) >= 2:
                rows.append({"instance": parts[0], "ip": parts[1],
                             "version": parts[2] if len(parts) > 2 else ""})
        return {"project_id": p.pid, "count": len(rows), "peripherals": rows}

    server.tool(
        "peripheral_list",
        "Every IP instance the loaded MCU provides, with its CubeMX IP version "
        "(`get mcu peripherals`).",
        S.obj({"project_id": S.s("Project id")}, ["project_id"]), peripheral_list)

    # ------------------------------------------------------------ ip params
    def ip_param_get(args: dict):
        p = _p(args)
        r = pm.run(p, f'get ip parameters "{args["ip"]}" "{args["param"]}"')
        text = r["output"].strip()
        value = ""
        m = re.search(r'"([^"]*)"', text)
        if m:
            value = m.group(1)
        return {"project_id": p.pid, "ip": args["ip"], "param": args["param"],
                "value": value, "raw": text, "status": r["status"]}

    server.tool(
        "ip_param_get",
        "Read one IP parameter (`get ip parameters <ip> <param>`).",
        S.obj({"project_id": S.s("Project id"), "ip": S.s("IP instance"),
               "param": S.s("Parameter name")},
              ["project_id", "ip", "param"]), ip_param_get)

    def ip_param_set(args: dict):
        p = _p(args)
        ip = args["ip"]
        ip = ip.strip('"')
        results = []
        # register the parameter in <IP>.IPParameters so it survives saveas
        if args.get("register", True):
            cur = pm.run(p, f'get ip parameters "{ip}" IPParameters')
            m = re.search(r'"([^"]*)"', cur["output"])
            current = m.group(1) if m and m.group(1) != "null" else ""
            names = [x for x in current.split(",") if x]
            if args["param"] not in names:
                names.append(args["param"])
            results.append(pm.run(p, f'set ip parameters "{ip}" IPParameters '
                                     f'{",".join(names)}'))
        results.append(pm.run(p, f'set ip parameters "{ip}" "{args["param"]}" '
                                 f'"{args["value"]}"'))
        ok = all(r["status"] == "OK" for r in results)
        read = pm.run(p, f'get ip parameters "{ip}" "{args["param"]}"')
        return {"project_id": p.pid, "ip": ip, "param": args["param"],
                "value": read["output"].strip(), "ok": ok}

    server.tool(
        "ip_param_set",
        "Set an IP parameter (`set ip parameters <ip> <param> <value>`). Also "
        "registers the name in `<IP>.IPParameters` so the value is persisted by "
        "project_save (CubeMX only writes listed parameters).",
        S.obj({"project_id": S.s("Project id"), "ip": S.s("IP instance"),
               "param": S.s("Parameter name"),
               "value": S.s("Value (numeric or CubeMX enum token)"),
               "register": S.b("Add to IPParameters list", True)},
              ["project_id", "ip", "param", "value"]), ip_param_set)

    def ip_params_set(args: dict):
        p = _p(args)
        out = []
        for name, value in (args.get("params") or {}).items():
            out.append({"param": name, "value": value})
        r = pm.run_many(p, [
            f'set ip parameters "{args["ip"]}" IPParameters '
            f'{",".join(list(args.get("params") or {}))}',
            *[f'set ip parameters "{args["ip"]}" "{k}" "{v}"'
              for k, v in (args.get("params") or {}).items()],
        ])
        return {"project_id": p.pid, "ip": args["ip"],
                "results": [{"command": x["command"], "status": x["status"]}
                            for x in r]}

    server.tool(
        "ip_params_set",
        "Set several IP parameters at once and register them all in IPParameters.",
        S.obj({"project_id": S.s("Project id"), "ip": S.s("IP instance"),
               "params": S.anyobj("name -> value map")},
              ["project_id", "ip", "params"]), ip_params_set)

    def ip_params_dump(args: dict):
        p = _p(args)
        if not p.ioc_path.exists():
            pm.save(p)
        ioc = p.ioc()
        result = {}
        for ip in args.get("ips") or ioc.ips:
            names = ioc.ip_parameters(ip)
            result[ip] = {n: ioc.get_ip_param(ip, n) for n in names}
        return {"project_id": p.pid, "parameters": result}

    server.tool(
        "ip_params_dump",
        "Dump every persisted parameter of the selected IPs from the saved .ioc "
        "(the authoritative view after project_save).",
        S.obj({"project_id": S.s("Project id"),
               "ips": S.arr("IP instances; default = all active", S.s("IP"))},
              ["project_id"]), ip_params_dump)

    def ip_user_name(args: dict):
        p = _p(args)
        r = pm.run(p, f'set username "{args["ip"]}" "{args["name"]}"')
        return {"project_id": p.pid, "ip": args["ip"], "user_name": args["name"],
                "status": r["status"]}

    server.tool(
        "ip_user_name",
        "Rename an IP instance (`set username <ip> <name>`), which changes the "
        "MX_/HAL_ symbol prefix in generated code.",
        S.obj({"project_id": S.s("Project id"), "ip": S.s("IP instance"),
               "name": S.s("New instance name")},
              ["project_id", "ip", "name"]), ip_user_name)

    # ------------------------------------------------------------ gpio/ioc
    def gpio_params(args: dict):
        p = _p(args)
        out = {}
        pins = [args["pin"]] if args.get("pin") else None
        ioc = p.ioc() if p.ioc_path.exists() else None
        if ioc is None:
            pm.save(p)
            ioc = p.ioc()
        for pin in (pins or ioc.pins):
            st = ioc.pin_state(pin)
            out[pin] = {"signal": st.signal, "mode": st.mode, "label": st.label,
                        "locked": st.locked,
                        "GPIOParameters": ioc.get(pin + ".GPIOParameters")}
        return {"project_id": p.pid, "pins": out}

    server.tool(
        "gpio_params",
        "GPIO parameters for one pin or all pins, read from the saved .ioc "
        "(GPIOParameters list, label, mode, lock state).",
        S.obj({"project_id": S.s("Project id"), "pin": S.s("Optional pin name")},
              ["project_id"]), gpio_params)

    def gpio_set(args: dict):
        """Write a GPIO parameter: `set gpio parameters <full pin> <param> <value>`
        (the pin must be the MCU pin name, e.g. PC13-TAMPER-RTC)."""
        p = _p(args)
        pin = _full_pin_name(pm, p, args["pin"])
        name, value = args["param"], args["value"]
        r = pm.run(p, f'set gpio parameters "{pin}" "{name}" "{value}"')
        method = "engine"
        if r["status"] != "OK":
            method = "ioc"
            ioc = p.ioc()
            params = [x for x in ioc.get(pin + ".GPIOParameters").split(",") if x]
            if name not in params:
                params.append(name)
            ioc.set(pin + ".GPIOParameters", ",".join(params))
            ioc.set(pin + "." + name, value.replace(":", "\\:"))
            ioc.save(p.ioc_path)
            if args.get("reload", True):
                pm.load_ioc(p, p.ioc_path)
        read = pm.run(p, f'get gpio parameters "{pin}" "{name}"')
        return {"project_id": p.pid, "pin": pin, "param": name, "value": value,
                "method": method, "engine_status": r["status"],
                "readback": read["output"].strip()}

    server.tool(
        "gpio_set",
        "Set a GPIO parameter (GPIO_Label, GPIO_Mode, GPIO_PuPd, GPIO_Speed, "
        "GPIO_OutputLevel...). Uses the engine when the CLI branch accepts it and "
        "otherwise edits the .ioc and reloads it, which produces the same file the "
        "GUI writes.",
        S.obj({"project_id": S.s("Project id"), "pin": S.s("Pin name"),
               "param": S.s("GPIO parameter name"),
               "value": S.s("Value, e.g. LED or GPIO_MODE_OUTPUT_PP"),
               "reload": S.b("Reload the .ioc after a direct edit", True)},
              ["project_id", "pin", "param", "value"]), gpio_set)
