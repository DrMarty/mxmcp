"""Targeted checks for the pieces the e2e flow exercises, run without a GUI.

Each case is small and independent so a failure names the exact CLI behaviour
that broke (prompt framing, pin naming, clock persistence, firmware gating).
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mxmcp.store import ProjectManager  # noqa: E402
from mxmcp.tools_pins import parse_modes, parse_pinout  # noqa: E402

WS = Path("build/unit_test").resolve()
FAILS: list[str] = []


def check(name: str, cond: bool, detail="") -> None:
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail else ""))
    if not cond:
        FAILS.append(name)


def main() -> int:
    shutil.rmtree(WS, ignore_errors=True)
    WS.mkdir(parents=True)
    pm = ProjectManager(max_open=1)
    pm.workspace = WS

    # ---------- pure parsers ----------
    check("parse_pinout dedupes doubled payload",
          parse_pinout("PA9: USART1_TXPA9: USART1_TX")[0]["signal"] == "USART1_TX")
    check("parse_modes dedupes repeated list",
          parse_modes("USART1: Asynchronous, USART1: Asynchronous, "
                      "USART1: Asynchronous, ")["USART1"] == ["Asynchronous"])
    check("parse_modes keeps distinct items",
          parse_modes("TIM1: Output Compare CH1, PWM Generation CH1")["TIM1"]
          == ["Output Compare CH1", "PWM Generation CH1"])

    # ---------- engine basics ----------
    p = pm.create("U1")
    info = pm.load_mcu(p, "STM32F103C8T6")
    check("part number resolves to RefName", info["mcu"] == "STM32F103C(8-B)Tx",
          info["mcu"])

    r = pm.run(p, "set pin PC13 GPIO_Output")
    check("short pin name accepted", r["status"] == "OK")
    pinout = {x["pin"]: x["signal"] for x in parse_pinout(pm.run(p, "get pinout")["output"])}
    check("PC13 mapped to GPIO_Output",
          pinout.get("PC13-TAMPER-RTC") == "GPIO_Output", pinout.get("PC13-TAMPER-RTC"))

    # gpio parameter through the engine (full pin name required)
    r = pm.run(p, 'set gpio parameters "PC13-TAMPER-RTC" "GPIO_Label" "LED"')
    read = pm.run(p, 'get gpio parameters "PC13-TAMPER-RTC" "GPIO_Label"')
    check("gpio label written via CLI", r["status"] == "OK" and "LED" in read["output"],
          read["output"])
    # persist now: an evicted engine would come back empty (no .ioc yet)
    pm.save(p)
    ioc = p.ioc()
    check("gpio label survives save", ioc.get("PC13-TAMPER-RTC.GPIO_Label") == "LED",
          ioc.get("PC13-TAMPER-RTC.GPIO_Label"))

    # clock parameters + HSE routing + persistence
    p_hse = pm.create("U0")
    pm.load_mcu(p_hse, "STM32F103C8T6")
    pm.run(p_hse, "set pin PC13 GPIO_Output")
    pm.run(p_hse, "project toolchain Makefile")
    pm.run(p_hse, "project name U0")
    pm.save(p_hse)
    pm.load_ioc(p_hse, p_hse.ioc_path)   # same path CubeMX takes after a restart
    r = pm.run(p_hse, 'set pin "PD0-OSC_IN" RCC_OSC_IN')
    r2 = pm.run(p_hse, 'set pin "PD1-OSC_OUT" RCC_OSC_OUT')
    check("HSE pins routable", r["status"] == "OK" and r2["status"] == "OK",
          f"{r['status']}/{r2['status']}")

    # CubeMX computes the derived RCC values during *save*, so the reliable
    # sequence is: write the tree -> save -> reload -> save again. The second save
    # is what persists the solved frequencies (verified: 8 MHz -> 72 MHz).
    clock_cmds = [
        'set ip parameters RCC IPParameters AHBFreq_Value,PLLMUL,PLLSourceVirtual,SYSCLKSource',
        'set ip parameters RCC AHBFreq_Value 72000000',
        'set ip parameters RCC PLLMUL RCC_PLL_MUL9',
        'set ip parameters RCC PLLSourceVirtual RCC_PLLSOURCE_HSE',
        'set ip parameters RCC SYSCLKSource RCC_SYSCLKSOURCE_PLLCLK',
        'clock resolution']
    for cmd in clock_cmds:
        pm.run(p_hse, cmd)
    pm.save(p_hse)                       # first save: parameters land
    pm.load_ioc(p_hse, p_hse.ioc_path)   # the solver re-evaluates on load
    pm.save(p_hse)                       # second save: solved values persist
    ioc_hse = p_hse.ioc()
    check("HSE tree solves to 72 MHz",
          ioc_hse.get_ip_param("RCC", "PLLCLKFreq_Value") == "72000000",
          ioc_hse.get_ip_param("RCC", "PLLCLKFreq_Value"))

    # ---------- generation (F1 package is installed) ----------
    out = WS / "gen"
    for cmd in ["project toolchain Makefile", "project name U1",
                f"project path {out}", "project generate"]:
        r = pm.run(p, cmd, timeout=300)
        check(f"generate step: {cmd.split()[1]}", r["status"] == "OK",
              f"{r['status']} {r['seconds']}s")
    files = [str(x.relative_to(out)) for x in out.rglob("*") if x.is_file()]
    check("main.c generated", any(f.endswith("main.c") for f in files), len(files))
    check("HAL driver copied", any("HAL_Driver" in f for f in files))
    check("Makefile generated", any(f.endswith("Makefile") for f in files))

    # ---------- firmware gating (offline, no engine) ----------
    p2 = pm.create("U2")
    p2.ioc_path.write_text(
        "#MicroXplorer Configuration settings - do not modify\n"
        "Mcu.Family=STM32H7\nMcu.Name=STM32H743ZITx\n"
        "ProjectManager.FirmwarePackage=STM32Cube FW_H7 V9.9.9\n"
        "ProjectManager.CustomerFirmwarePackage=\n", encoding="iso-8859-1")
    from mxmcp.tools_generate import _fw_state
    st = _fw_state(p2, {})
    check("missing H7 package detected", st["available"] is False,
          json.dumps({"pinned": st["pinned_in_ioc"], "installed": st["installed"]}))
    p3 = pm.create("U3")
    p3.ioc_path.write_text(
        "#MicroXplorer Configuration settings - do not modify\n"
        "Mcu.Family=STM32F1\nMcu.Name=STM32F103C(8-B)Tx\n"
        "ProjectManager.FirmwarePackage=STM32Cube FW_F1 V1.8.0\n"
        "ProjectManager.CustomerFirmwarePackage=\n", encoding="iso-8859-1")
    st = _fw_state(p3, {})
    check("installed F1 package accepted", st["available"] is True,
          json.dumps({"pinned": st["pinned_in_ioc"], "installed": st["installed"]}))

    pm.close_all()
    print("\nFAILURES:", FAILS or "none")
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())

