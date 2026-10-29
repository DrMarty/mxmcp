"""Clock tree tools.

CubeMX solves the clock tree inside the engine; the CLI exposes it as RCC
parameters. Every write registers the parameter in `RCC.IPParameters` so
`project_save` persists it (verified: without registration the value stays in
memory only and the .ioc keeps the old derived frequencies).
"""
from __future__ import annotations

from . import schema as S
from .rpc import ToolError
from .store import ProjectManager

# CubeMX derives these from the tree; they are read-only outputs.
DERIVED = {
    "HCLKFreq_Value", "SYSCLKFreq_VALUE", "PLLCLKFreq_Value", "PLLMCOFreq_Value",
    "PLLCLKFreq_value", "APB1Freq_Value", "APB2Freq_Value", "APB1TimFreq_Value",
    "APB2TimFreq_Value", "FCLKCortexFreq_Value", "TimSysFreq_Value",
    "MCOFreq_Value", "USBFreq_Value", "ADCFreq_Value", "VCOOutputFreq_Value",
    "VCOOutputFreq_Value2", "VCOInputFreq_Value",
}


def _rcc_params(ioc) -> dict:
    out = {}
    for name in ioc.ip_parameters("RCC"):
        out[name] = ioc.get_ip_param("RCC", name)
    return out


def _pass(pm, p, params, routed, save: bool) -> dict:
    plan = [["HSE_VALUE", "HSI_VALUE", "LSE_VALUE", "LSI_VALUE"],
            ["PLLSourceVirtual", "PLLSource", "PLLMUL"],
            ["SYSCLKSource", "AHBCLKDivider", "APB1CLKDivider",
             "APB2CLKDivider"],
            ["AHBFreq_Value"]]
    seen: set[str] = set()
    for group in plan:
        keys = [k for k in group if k in params]
        if not keys:
            continue
        seen.update(keys)
        pm.run(p, f'set ip parameters RCC IPParameters {",".join(keys)}')
        for k in keys:
            r = pm.run(p, f'set ip parameters RCC "{k}" "{params[k]}"')
            if r["status"] != "OK":
                raise ToolError(f"clock parameter rejected: {k} -> "
                                f"{r['output'][:200]}")
    rest = [k for k in params if k not in seen]
    if rest:
        pm.run(p, f'set ip parameters RCC IPParameters {",".join(rest)}')
        for k in rest:
            pm.run(p, f'set ip parameters RCC "{k}" "{params[k]}"')
    pm.run(p, "clock resolution")
    if save:
        pm.save(p)
    ioc = p.ioc() if p.ioc_path.exists() else None
    now = _rcc_params(ioc) if ioc else {}
    derived = {k: v for k, v in now.items() if k in DERIVED and v not in ("", "null")}
    ok = True
    for key in ("AHBFreq_Value", "PLLMUL", "SYSCLKSource", "PLLSourceVirtual"):
        if str(params.get(key, "")) and now.get(key) != str(params[key]):
            ok = False
    return {"params_now": now, "derived": derived, "applied_ok": ok,
            "hse_routed": routed}


def _requested_met(params: dict, now: dict) -> bool:
    for key in ("AHBFreq_Value", "PLLMUL", "SYSCLKSource", "PLLSourceVirtual",
                "APB1CLKDivider", "APB2CLKDivider"):
        want = str(params.get(key, ""))
        if want and now.get(key) != want:
            return False
    return True


def register(server, pm: ProjectManager) -> None:
    def clock_get(args: dict):
        p = pm.get(args["project_id"])
        if not p.ioc_path.exists():
            pm.save(p)
        ioc = p.ioc()
        params = _rcc_params(ioc)
        derived = {k: v for k, v in params.items() if k in DERIVED}
        direct = {k: v for k, v in params.items() if k not in DERIVED}
        # live values straight from the engine (may differ before a save)
        live = {}
        for name in (args.get("params") or list(derived)):
            r = pm.run(p, f'get ip parameters RCC "{name}"')
            text = r["output"].strip()
            if '"' in text:
                live[name] = text.split('"')[1]
        return {"project_id": p.pid, "mcu": ioc.mcu_name,
                "derived_frequencies": derived, "settings": direct,
                "live": live}

    server.tool(
        "clock_get",
        "Clock tree state: derived frequencies (HCLK/SYSCLK/PCLK/...) and the "
        "RCC settings that produce them, read from the saved .ioc plus live reads.",
        S.obj({"project_id": S.s("Project id"),
               "params": S.arr("Extra RCC parameter names to read live",
                               S.s("param"))},
              ["project_id"]), clock_get)

    def clock_set(args: dict):
        p = pm.get(args["project_id"])
        params = dict(args.get("params") or {})
        for k in ("sysclk_hz",):
            if args.get(k) is not None:
                params["AHBFreq_Value"] = str(args[k])
        for k in ("pll_mul",):
            if args.get(k):
                params["PLLMUL"] = str(args[k])
        if args.get("pll_source"):
            params["PLLSourceVirtual"] = args["pll_source"]
        if args.get("sysclk_source"):
            params["SYSCLKSource"] = args["sysclk_source"]
        if args.get("ahb_div"):
            params["AHBCLKDivider"] = args["ahb_div"]
        if args.get("apb1_div"):
            params["APB1CLKDivider"] = args["apb1_div"]
        if args.get("apb2_div"):
            params["APB2CLKDivider"] = args["apb2_div"]
        for k in ("hse_mhz", "hsi_mhz", "lse_khz", "lsi_khz"):
            if args.get(k) is not None:
                key = {"hse_mhz": "HSE_VALUE", "hsi_mhz": "HSI_VALUE",
                       "lse_khz": "LSE_VALUE", "lsi_khz": "LSI_VALUE"}[k]
                params[key] = str(args[k])
        if not params:
            raise ToolError("no clock parameters supplied")

        # Selecting PLL from HSE is only legal with the HSE pins muxed to the
        # oscillator (the GUI does this automatically; the CLI does not).
        routed = []
        wants_hse = str(params.get("PLLSourceVirtual", "")).endswith("_HSE")
        if wants_hse and args.get("route_hse", True):
            routed = _route_hse(pm, p, args)

        # Clock parameters must be written through the GUI-style channel: the
        # plain `set ip parameters` list endpoint registers the name but does not
        # re-solve the tree, while the `IPParameters` form re-assigns the value
        # and re-runs the solver for that sheet.
        save = args.get("save", True)
        state = _pass(pm, p, params, routed, save)
        # A freshly written tree keeps the default derived frequencies until
        # CubeMX re-opens it: save + reload, then one more pass makes the solver
        # evaluate the new settings (verified on F1: 8 MHz -> 72 MHz). F4 already
        # converges in the first pass, so the extra cycle only runs when needed.
        passes = 1
        while save and not _requested_met(params, state["params_now"]) and passes < 4:
            pm.load_ioc(p, p.ioc_path)
            state = _pass(pm, p, params, routed, save)
            passes += 1
        params_now = state["params_now"]
        derived = state["derived"]
        applied_ok = state["applied_ok"]
        warning = ""
        if save:
            # A rejected solve leaves the previous values in place: report what
            # CubeMX computed rather than echoing the request.
            if not applied_ok:
                warning = ("CubeMX kept the previous tree (the .ioc still holds "
                           f"AHB={params_now.get('AHBFreq_Value')}, "
                           f"PLL={params_now.get('PLLMUL')}, "
                           f"PLLCLK={params_now.get('PLLCLKFreq_Value')}). Check "
                           "the crystal pins (hse_pins) and the family's maximum "
                           "frequencies.")
            elif str(params.get("PLLSourceVirtual", "")).endswith("_HSE") and \
                    derived.get("PLLCLKFreq_Value") in (None, "8000000"):
                warning = ("HSE is selected but the tree still solves from HSI: "
                           "mux the crystal pins (hse_pins, e.g. PD0/PD1 on F1, "
                           "PH0/PH1 on F4) or set hse_mhz.")
            return {"project_id": p.pid, "applied": params,
                    "applied_ok": applied_ok,
                    "derived_frequencies": derived,
                    "hse_routed": routed,
                    "warning": warning}
        return {"project_id": p.pid, "applied": params, "saved": False,
                "hse_routed": routed}

    def _route_hse(pm, p, args) -> list[str]:
        """Route the crystal the way the GUI does.

        The GUI enables the RCC mode (`set mode RCC "Crystal/Ceramic Resonator"`),
        which muxes OSC_IN/OSC_OUT automatically. If the board has no such mode
        (some families expose `HSE-External-Oscillator` instead) the pins are set
        explicitly; `set pin` alone does NOT re-solve the tree on F1, which is why
        the mode comes first.
        """
        done: list[str] = []
        modes = pm.run(p, "get modes RCC")["output"].lower()
        for mode in ("crystal/ceramic resonator", "hse-external-oscillator",
                     "bypass clock source"):
            if mode in modes:
                cmd = f'set mode RCC "{mode.title()}"'
                # keep CubeMX's exact spelling of the mode name
                for raw in ["Crystal/Ceramic Resonator",
                            "HSE-External-Oscillator", "BYPASS Clock Source"]:
                    if raw.lower() == mode:
                        cmd = f'set mode RCC "{raw}"'
                r = pm.run(p, cmd)
                if r["status"] == "OK":
                    done.append(cmd)
                break

        pinout = pm.run(p, "get pinout")["output"]
        names = [line.split(":", 1)[0].strip() for line in pinout.splitlines()
                 if ":" in line]
        hints = [h.upper() for h in (args.get("hse_pins") or [])]
        for name in names:
            base = name.split("-")[0]
            if "OSC32" in name.upper():
                continue
            if not (base.endswith("OSC_IN") or base.endswith("OSC_OUT")):
                continue
            if hints and not any(h in name.upper() for h in hints):
                continue
            sig = "RCC_OSC_IN" if base.endswith("OSC_IN") else "RCC_OSC_OUT"
            cmd = f'set pin "{name}" {sig}'
            if pm.run(p, cmd)["status"] == "OK":
                done.append(cmd)
        return done

    server.tool(
        "clock_set",
        "Program the clock tree. Accepts explicit RCC parameters or the friendly "
        "keys: sysclk_hz, pll_mul, pll_source, sysclk_source, ahb_div, apb1_div, "
        "apb2_div, hse_mhz, hsi_mhz, lse_khz, lsi_khz. Runs `clock resolution` so "
        "CubeMX re-solves the tree, then saves and returns the derived frequencies.",
        S.obj({
            "project_id": S.s("Project id"),
            "params": S.anyobj("Raw RCC parameter map, e.g. {PLLMUL: RCC_PLL_MUL9}"),
            "sysclk_hz": S.i("Target HCLK in Hz (writes AHBFreq_Value)"),
            "pll_mul": S.s("PLL multiplier token (RCC_PLL_MUL9 / PLLMUL9)"),
            "pll_source": S.s("PLL source (RCC_PLLSOURCE_HSE / HSI_DIV2)"),
            "sysclk_source": S.s("RCC_SYSCLKSOURCE_PLLCLK / HSI / HSE"),
            "ahb_div": S.s("AHB prescaler (RCC_SYSCLK_DIV1)"),
            "apb1_div": S.s("APB1 prescaler (RCC_HCLK_DIV2)"),
            "apb2_div": S.s("APB2 prescaler (RCC_HCLK_DIV1)"),
            "hse_mhz": S.s("HSE crystal value in MHz"),
            "hsi_mhz": S.s("HSI value in MHz"),
            "lse_khz": S.s("LSE value in kHz"),
            "lsi_khz": S.s("LSI value in kHz"),
            "route_hse": S.b("Mux OSC_IN/OSC_OUT to HSE when PLL sources from HSE", True),
            "hse_pins": S.arr("Pin hints for the crystal (F1: PD0/PD1, F4/H7: PH0/PH1)", S.s("PD0")),
            "save": S.b("Persist to the .ioc", True),
        }, ["project_id"]), clock_set)

    def clock_resolve(args: dict):
        p = pm.get(args["project_id"])
        r = pm.run(p, "clock resolution")
        out = {"project_id": p.pid, "resolution": r["status"]}
        if args.get("save", True):
            out.update(pm.save(p))
        return out

    server.tool(
        "clock_resolve",
        "Run CubeMX's clock issue resolver (`clock resolution`) and re-save.",
        S.obj({"project_id": S.s("Project id"),
               "save": S.b("Persist after resolving", True)},
              ["project_id"]), clock_resolve)

    def clock_param_values(args: dict):
        p = pm.get(args["project_id"])
        r = pm.run(p, f'get mode_param_possvalue RCC "{args["param"]}"')
        return {"project_id": p.pid, "param": args["param"],
                "status": r["status"], "values": r["output"].strip()}

    server.tool(
        "clock_param_possible_values",
        "Query the allowed values of one RCC parameter "
        "(`get mode_param_possvalue`).",
        S.obj({"project_id": S.s("Project id"), "param": S.s("RCC parameter")},
              ["project_id", "param"]), clock_param_values)

