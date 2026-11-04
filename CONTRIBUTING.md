# Contributing Guide

Thanks for contributing. The goal of this project is to **fully expose STM32CubeMX's project capabilities through MCP,
and to make them usable on machines without CubeMX as well**.

## 1. Environment

```bash
python -m venv .venv && . .venv/Scripts/activate     # Windows: .venv\Scripts\activate
python -m pip install -e ".[dev]"
```

The repository **does not contain** any ST-derived data (see THIRD-PARTY NOTICES in [LICENSE](../LICENSE)).
To run the full feature set locally:

```bash
# With CubeMX (hybrid mode)
set MXMCP_CUBEMX_ROOT=C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX

# Code only (standalone mode): generate the data pack first
python -m mxmcp.bundle build --cubemx-root "C:\Program Files\...\STM32CubeMX"
python -m mxmcp.bundle verify
```

`mxmcp/data/*.zip`, `analysis/`, and `docs/javap/` are all ignored via `.gitignore`;
`tools/check_compliance.py` enforces this in CI.

## 2. Code structure

```
mxmcp/
├── rpc.py            MCP/JSON-RPC 2.0 (newline-delimited; Content-Length framing also accepted)
├── server.py         Entry point: --selftest --list-tools --call
├── engine.py         CubeMX session (-i resident; framing/timeouts/hang recovery)
├── store.py          Project pool, save/reload, part number resolution
├── ioc.py            .ioc read/write (including merged view with project_ext.ioc)
├── catalog.py        Install directory db index; falls back to data pack when not installed
├── bundle.py         Data pack build/info/verify + Pack reading
├── standalone.py     Standalone engine (pins/modes/parameters/NVIC, real validation)
├── ipmodes.py        IP modes and parameter schema
├── codegen.py        Standalone C code generation (driven by HAL Init parameter trees)
├── firmware.py       Firmware package integrity scan
└── tools_*.py        113 MCP tools, split by family
```

## 3. Hard requirements for changes

1. **Do not bypass the engine's framing rules**. CubeMX responses come in three forms: a standalone terminator line,
   a terminator glued to the end of the body text, and responses on log4j lines; `engine.py` handles all of them, so please preserve that when making changes.
2. **Parameters must be registered**. When writing `<IP>.<param>`, also write it into `<IP>.IPParameters`; otherwise
   CubeMX discards it on reload (both `standalone.py` and the tool layer follow this rule).
3. **Use full pin names** (`PC13-TAMPER-RTC`); the tool layer is responsible for resolving them from short names.
4. **Do not run `load <part number>` directly for an unknown MCU**: it makes the interpreter hang forever; it must first be resolved to a
   db RefName (`Catalog.resolve_mcu`).
5. **Offline first**. Any capability that depends only on data must work without an installation
   (the branches in `catalog`/`bundle`/`standalone`/`ipmodes`/`codegen` are examples).
6. **Do not commit ST-derived files**. CI will reject them.

## 4. Testing

```bash
pytest tests -q                  # Unit tests (no CubeMX needed)
python tests/test_standalone.py  # Points the install path at a nonexistent directory to verify standalone mode
python tests/test_e2e.py         # Requires CubeMX (hybrid)
python tests/test_advanced.py    # Newly added dma/nvic/gic/mmt/porting, etc.
python tests/test_rtos.py        # RTOS object read/write
python tests/test_middleware.py  # Middleware integration
```

PR requirements: `ruff check .` is clean, relevant tests pass, and README/docs are updated accordingly.

## 5. Reverse-engineering evidence

The scripts under `tools/` are reproducible forensic tools (javap scanning, data pack building, CLI probes, etc.).
When submitting reverse-engineering-related changes, please state which `analysis/*.json` file or which measured output a conclusion comes from;
do not write documentation from memory — every table in docs should be traceable to a script artifact.

## 6. License

By submitting, you agree to release your contribution under the MIT license (see LICENSE). Parts involving ST content
(data pack, decompiled artifacts) are outside the scope of contributions.
