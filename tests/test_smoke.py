"""Pytest-collectable smoke tests: they need no CubeMX and no engine.

The other scripts in `tests/` are runnable end-to-end programs (they start the MCP
server and, for some, the CubeMX engine). These functions give CI something cheap
and deterministic to assert on every push: the protocol layer, the `.ioc` model,
the standalone engine and the redistribution policy.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mxmcp import __version__  # noqa: E402
from mxmcp.bundle import Pack  # noqa: E402
from mxmcp.ioc import IocProject  # noqa: E402
from mxmcp.rpc import McpServer  # noqa: E402


# ------------------------------------------------------------------ protocol
def test_version():
    assert __version__ and __version__.count(".") == 2


def test_protocol_initialize():
    srv = McpServer(name="mxmcp", version=__version__)
    res = srv.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                      "params": {"protocolVersion": "2024-11-05"}})
    assert res["result"]["serverInfo"]["name"] == "mxmcp"
    assert "tools" in res["result"]["capabilities"]


def test_protocol_ping_and_unknown_method():
    srv = McpServer(name="mxmcp", version=__version__)
    assert srv.handle({"jsonrpc": "2.0", "id": 2, "method": "ping"})["result"] == {}
    bad = srv.handle({"jsonrpc": "2.0", "id": 3, "method": "nope"})
    assert "error" in bad


def test_server_registers_all_tool_families(tmp_path: Path):
    from mxmcp import (
        tools_advanced,
        tools_catalog,
        tools_cli,
        tools_clock,
        tools_generate,
        tools_middleware,
        tools_pack,
        tools_pins,
        tools_project,
        tools_rtos,
        tools_standalone,
    )
    from mxmcp.store import ProjectManager

    srv = McpServer(name="mxmcp", version=__version__)
    # a ProjectManager only indexes the database here; no JVM is started
    pm = ProjectManager(max_open=1)
    pm.workspace = tmp_path
    for mod in (tools_project, tools_catalog, tools_pins, tools_clock,
                tools_generate, tools_pack, tools_cli, tools_advanced,
                tools_rtos, tools_middleware, tools_standalone):
        try:
            mod.register(srv, pm)
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"{mod.__name__}.register failed: {exc}")
    assert len(srv.tools) >= 100
    names = set(srv.tools)
    for expected in ("project_create", "pin_set", "clock_set", "rtos_objects",
                     "standalone_generate", "dma_query", "command_catalog"):
        assert expected in names, f"missing tool {expected}"
    pm.close_all()


# ------------------------------------------------------------------- .ioc
def test_ioc_roundtrip(tmp_path: Path):
    p = tmp_path / "a.ioc"
    ioc = IocProject()
    ioc.set("Mcu.Name", "STM32F103C(8-B)Tx")
    ioc.set("Mcu.Pin0", "PC13-TAMPER-RTC")
    ioc.set("PC13-TAMPER-RTC.Signal", "GPIO_Output")
    ioc.set("USART1.IPParameters", "BaudRate")
    ioc.set("USART1.BaudRate", "115200")
    ioc.save(p)
    back = IocProject.load(p)
    assert back.get("Mcu.Name") == "STM32F103C(8-B)Tx"
    assert back.get("USART1.BaudRate") == "115200"
    assert back.pin_state("PC13-TAMPER-RTC").signal == "GPIO_Output"


# ------------------------------------------------------------- data pack
@pytest.fixture(scope="module")
def pack() -> Pack:
    p = Pack()
    if not p.available:
        pytest.skip("data pack not built: run `python -m mxmcp.bundle build`")
    return p


def test_pack_meta(pack: Pack):
    meta = pack.meta()
    counts = meta["counts"]
    assert counts["mcu"] > 1500
    assert counts["pins"] > 100_000
    assert counts["ip_modes"] > 200


def test_pack_lookup_and_marketing_name(pack: Pack):
    hits = pack.find("STM32F103C8", limit=5)
    assert any(r["ref_name"].startswith("STM32F103C") for r in hits)
    row = pack.mcu("STM32F103C(8-B)Tx")
    assert row and row["family"].startswith("STM32F1")
    assert any(p["name"].startswith("PA9") for p in row["pins"])


# --------------------------------------------------------- standalone engine
def test_standalone_engine_validation(pack: Pack):
    from mxmcp.standalone import DeviceDB, StandaloneError, StandaloneProject

    db = DeviceDB(pack)
    prj = StandaloneProject.create(db, "STM32F103C8T6", pid="smoke")
    assert prj.device and prj.device.ref_name.startswith("STM32F103C")

    prj.set_pin("PA9", "USART1_TX")            # valid
    prj.set_pin("PC13", "GPIO_Output")          # GPIO pseudo-signal expanded
    with pytest.raises(StandaloneError):
        prj.set_pin("PA9", "USART3_TX")         # not on this pin
    with pytest.raises(StandaloneError):
        prj.set_pin("PZ99", "GPIO_Output")      # no such pin

    prj.set_mode("USART1", "Asynchronous")
    prj.set_ip_param("USART1", "BaudRate", "115200")
    prj.set_nvic("USART1_IRQn", priority=1, enabled=True)
    assert prj.problems() == []

    text = prj.to_ioc().dumps()
    assert "USART1.IPParameters" in text
    assert "USART1.BaudRate=115200" in text
    assert "USART1_IRQn" in text


def test_standalone_codegen(pack: Pack, tmp_path: Path):
    from mxmcp.codegen import Generator
    from mxmcp.standalone import DeviceDB, StandaloneProject

    prj = StandaloneProject.create(DeviceDB(pack), "STM32F103C8T6", pid="gen")
    prj.set_pin("PA9", "USART1_TX")
    prj.set_mode("USART1", "Asynchronous")
    prj.set_ip_param("USART1", "BaudRate", "9600")
    res = Generator(prj).generate(tmp_path, project_name="gen")
    assert res["file_count"] >= 5
    main_c = (tmp_path / "Core" / "Src" / "main.c").read_text(encoding="utf-8")
    assert "MX_USART1_Init" in main_c
    assert "BaudRate = 9600" in main_c


# ------------------------------------------------------------- ip modes
def test_ip_modes_catalog(pack: Pack):
    from mxmcp.ipmodes import IPModes

    im = IPModes(pack)
    assert "CMSIS_V2" in im.modes("FREERTOS")
    assert "SDIO" in im.modes("FATFS")
    assert im.parameters("USART1") or im.parameters("USART")


# ------------------------------------------------------------- compliance
def test_redistribution_policy_is_declared():
    """The repo must keep ST-derived artifacts out of version control."""
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for needle in ("mxmcp/data/cubemx-db.zip", "analysis/", "docs/javap/"):
        assert needle in gitignore, f".gitignore must exclude {needle}"
    licence = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "THIRD-PARTY NOTICES" in licence
    assert (ROOT / "tools" / "check_compliance.py").exists()


def test_pack_path_env_override(monkeypatch, tmp_path: Path):
    from mxmcp.bundle import pack_path as pp
    monkeypatch.setenv("MXMCP_DATA_PACK", str(tmp_path / "x.zip"))
    assert pp() == tmp_path / "x.zip"
