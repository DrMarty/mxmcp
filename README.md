# mxmcp — An MCP server for STM32CubeMX (can also run fully standalone)

> Deliverables: `mxmcp/` (server source + bundled data pack), `tests/` (6 test scripts),
> `docs/` (reverse-engineering notes, architecture, data model, feature matrix, standalone mode, acceptance),
> `analysis/` (machine-readable reverse-engineering artifacts), `tools/` (reproducible forensic scripts).

Two modes, one MCP interface:

* **hybrid**: when CubeMX is installed, drives the official engine (pin/clock/generation behavior is genuine ST behavior).
* **standalone**: **no CubeMX installation required** — ships with a 9.1 MB data pack
  (2 019 MCUs / 245 083 pins / 274 IP mode sets / HAL Init parameter trees),
  plus a built-in validation engine and C code generator. See [docs/STANDALONE.md](docs/STANDALONE.md).

```
Project state (.ioc)  ←→  mxmcp (Python MCP server)  ←→  CubeMX CLI (resident JVM, optional)
                              ↑
                   Bundled data pack cubemx-db.zip (offline selection/validation/generation)
```

## 1. Why this approach

* CubeMX 6.15.0 is a **Java application packaged as a PE32 loader + embedded ZIP** (not a native-image,
  **no unpacking needed**): `java -jar STM32CubeMX.exe -q script.txt` is the official headless entry point;
  the embedded archive has 54 774 entries, starting at `0x13000`, with the central directory at `0xD2F0A03`
  (`tools/rebuild_full_jar.py` rebuilds it in full, 0 failures).
* Internally the engine has **267** CLI registrations (older notes listed only 89, because the earlier extraction missed
  `com/st/components`) and 217 plugin opcodes; `export script` can serialize any project into
  replayable commands.
* So the MCP server does not "reimplement CubeMX"; it is a **controlled front end**: write operations go through the official interpreter,
  read operations read the `.ioc`/bundled data pack; the two can be cross-checked (`verify` / `standalone_validate`).

Full reverse-engineering notes: [ARCHITECTURE.md](docs/ARCHITECTURE.md) (overview) ·
[REVERSE_ENGINEERING.md](docs/REVERSE_ENGINEERING.md) (process) ·
[DATA_MODEL.md](docs/DATA_MODEL.md) (data structures) ·
[CLI_REGISTRY.md](docs/CLI_REGISTRY.md) (267 commands) ·
[FEATURES.md](docs/FEATURES.md) (feature coverage matrix) ·
[SECURITY_NETWORK.md](docs/SECURITY_NETWORK.md) (trust chain and endpoints) ·
[STANDALONE.md](docs/STANDALONE.md) (standalone mode)

## 2. Requirements

* Python 3.9+ (**zero third-party dependencies**, standard library only)
* STM32CubeMX is **optional**:
  * Installed → hybrid mode, uses the official engine (default path
    `C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX`)
  * Not installed → standalone mode; build the data pack once first with
    `python -m mxmcp.bundle build --cubemx-root <install dir>` (requires a machine with CubeMX installed)
* Note: the repository **does not include** the data pack (ST-derived content, see [LICENSE](LICENSE)).

Environment variables (optional):

| Variable | Purpose | Default |
|---|---|---|
| `MXMCP_CUBEMX_ROOT` | CubeMX installation directory | `C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX` |
| `MXMCP_WORKSPACE` | Project state directory | `~/.mxmcp` |
| `MXMCP_MAX_ENGINES` | Number of concurrently resident JVMs (one per open project) | `3` |

## 3. Connecting an MCP client

stdio transport, JSON-RPC 2.0 (newline-delimited; `Content-Length` framing is also accepted).

```json
{
  "mcpServers": {
    "stm32cubemx": {
      "command": "python",
      "args": ["-m", "mxmcp.server"],
      "cwd": "C:\\path\\to\\mxmcp",
      "env": { "MXMCP_WORKSPACE": "C:\\Users\\me\\.mxmcp" }
    }
  }
}
```

Self-check:

```bat
python -m mxmcp.server --list-tools
python -m mxmcp.server --selftest
python -m mxmcp.server --call catalog_index --args {}
```

## 4. Five-minute quick start

```text
project_create {name: "blink", mcu: "STM32F103C8T6", toolchain: "Makefile"}
  -> project_id = blink
mcu_pin_functions {project_id: "blink", pin: "PA9"}      # see available signals
pin_set   {project_id: "blink", pin: "PC13", signal: "GPIO_Output"}
pin_set   {project_id: "blink", pin: "PA9",  signal: "USART1_TX"}
pin_set   {project_id: "blink", pin: "PA10", signal: "USART1_RX"}
mode_set  {project_id: "blink", peripheral: "USART1", mode: "Asynchronous"}
ip_param_set {project_id: "blink", ip: "USART1", param: "BaudRate", value: "115200"}
gpio_set  {project_id: "blink", pin: "PC13", param: "GPIO_Label", value: "LED"}
clock_set {project_id: "blink", sysclk_hz: 72000000, pll_mul: "RCC_PLL_MUL9",
           pll_source: "RCC_PLLSOURCE_HSE", sysclk_source: "RCC_SYSCLKSOURCE_PLLCLK",
           apb1_div: "RCC_HCLK_DIV2"}
project_save   {project_id: "blink"}
verify         {project_id: "blink"}
project_generate {project_id: "blink", output_dir: "D:/work/blink", toolchain: "Makefile"}
```

`project_generate` returns the file list and warnings; a typical result: 913 files, `Src/main.c`, `Drivers/`,
`Makefile`, `.ioc`, taking about 5–10 seconds (with the engine warm).

## 5. Tool overview (113)

**Project lifecycle**: `project_create` `project_list` `project_get` `project_open`
`project_close` `project_save` `project_save_as` `project_delete` `project_diff`
`project_load_mcu` `project_load_board` `project_import_config` `project_export_script`
`project_options` `project_set_option` `project_report` `project_csv` `project_files`

**Selection / reference data (offline)**: `catalog_index` `mcu_search` `mcu_info` `mcu_pin_functions`
`family_list` `family_mcus` `board_search` `board_list` `ip_library` `template_list`
`firmware_packages` `mode_catalog` `command_catalog` `product_db` `middleware_list`

**Pins / peripherals**: `pinout_get` `pin_functions` `pin_set` `pin_reset` `pin_clear_all`
`pin_lock` `pin_reserve` `gpio_params` `gpio_set` `peripheral_list` `mode_list`
`mode_set` `mode_reset` `mode_check` `sub_modes` `submode_state` `mode_pattern`
`ip_param_get` `ip_param_set` `ip_params_set` `ip_params_dump` `ip_user_name`
`value_check`

**Interrupts / DMA / memory map**: `nvic_read` `nvic_write` `dma_query` `dma_mutate`
`mdma_query` `mdma_mutate` `gic_query` `gic_mutate` `mmt` `lpbam`

**RTOS / middleware**: `rtos_schema` `rtos_status` `rtos_objects` `rtos_object_write`
`rtos_config` `middleware_add`

**Clock**: `clock_get` `clock_set` `clock_resolve` `clock_param_possible_values`

**Generation / validation**: `project_generate` `generate_code` `verify` `compliance`

**Porting / comparison / selectors**: `porting` `ioc_compare` `selectors`

**Software packs**: `pack_status` `pack_enable` `pack_disable` `pack_validate` `swmgr`
`xcubedl` `login` `logout`

**Standalone mode (no installation)**: `standalone_info` `standalone_create` `standalone_open`
`standalone_pin` `standalone_signals` `standalone_mode` `standalone_param`
`standalone_nvic` `standalone_view` `standalone_validate` `standalone_generate`
`standalone_mcu`

**Direct `.ioc` writes / fallback / runtime**: `ioc_get` `ioc_set` `ioc_delete` `ioc_import`
`ioc_export` `cli` `cli_batch` `cli_help` `runtime_props` `ide_bridge`

`cli` / `cli_batch` can execute **any** command in [CLI_REGISTRY](docs/CLI_REGISTRY.md)
(267 commands), so the MCP interface is a superset of the CubeMX CLI: even if a capability has no dedicated tool, nothing is lost.
For the full feature → command → tool mapping, see [docs/FEATURES.md](docs/FEATURES.md).

## 6. Key behaviors and pitfalls (already handled in code)

1. **`load` only accepts the db RefName**: `STM32F103C8T6` makes the interpreter hang forever; `project_create`
   first resolves the part number to `STM32F103C(8-B)Tx` using the local database.
2. **Unregistered parameters are not persisted**: `ip_param_set`/`clock_set` automatically add the parameter name to `<IP>.IPParameters`.
3. **`config save` hangs when no path is given**: only `saveas`/`saveext` are used, and the result is read back and verified after saving.
4. **A hung engine contaminates subsequent calls**: the session engine's process is killed on timeout, and the next call automatically recovers via `config load`;
   `hung: true` in the return value reports this explicitly.
5. **Firmware package versions must match**: when `FirmwarePackage` in the `.ioc` does not match the actual install directory,
   `project generate` tries to go online (which may hang without a UI). A pre-check runs before generation; if the package is missing, it automatically
   uses `project setCustomFWPath` to point to an installed package of the same family, re-pins the version, and then generates.
6. **The first generation may only copy drivers**: CubeMX occasionally only copies drivers on the first pass; the tool detects
   "Drivers present but no main.c" and automatically generates again.
7. **GPIO parameters need the full pin name**: `PC13` → `PC13-TAMPER-RTC`; the tool resolves this automatically.
8. **HSE clock tree**: setting only `PLLSourceVirtual=HSE` without remapping the OSC pins still solves the clock tree using HSI;
   `clock_set` automatically remaps `OSC_IN/OSC_OUT` to `RCC_OSC_IN/OUT` and includes a warning in the result.
9. **Derived clock values need two saves**: CubeMX only computes derived values such as `PLLCLKFreq_Value` on *save*.
   The reliable sequence is **write → save → reload → save** (measured 8 MHz → 72 MHz); this is built into
   `clock_set`'s multi-pass convergence. When reproducing manually with `cli`, be sure to follow this order.
10. **Don't rely on an already-started engine when there is no `.ioc`**: an engine that is recycled and restarted comes up with an empty project,
    and `config saveas` throws a `Mcu.getDie()` NPE. Run `project_save` once first, then continue.
11. **`set mode` for middleware IPs takes no quotes**: `set mode FREERTOS CMSIS_V2`; `get modes`
    returns KO for middleware, so `mode_list` automatically falls back to `db/mcu/IP/*_Modes.xml`.
12. **RTOS objects exist only in the extended save**: only `project_ext.ioc` contains `FREERTOS.Tasks01` etc.;
    reading state requires a merged view, and after writing, the engine must reload once.

## 7. Directory layout

```
mxmcp/
├── mxmcp/                    Server source (zero third-party dependencies)
│   ├── server.py             MCP entry point (stdio; --selftest/--list-tools/--call)
│   ├── rpc.py                JSON-RPC 2.0 / MCP protocol
│   ├── engine.py             CubeMX session engine (-i resident + three framing modes)
│   ├── store.py              Project pool, save/load, part number resolution
│   ├── ioc.py                .ioc read/write (including project_ext.ioc merged view)
│   ├── catalog.py            Install directory index (falls back to data pack when not installed)
│   ├── bundle.py             Data pack build/info/verify + Pack reading
│   ├── standalone.py         Standalone engine (pins/modes/parameters/NVIC, real validation)
│   ├── ipmodes.py            IP modes and parameter schema
│   ├── codegen.py            Standalone C code generation
│   ├── firmware.py           Firmware package integrity scan
│   └── tools_*.py            113 MCP tools
├── tests/                    6 test scripts
│   ├── test_units.py         Parsing/parameters/firmware pre-check (including real generation)
│   ├── test_e2e.py           Full MCP flow (F1/F4/boards)
│   ├── test_advanced.py      dma/nvic/gic/mmt/porting/selectors/catalog
│   ├── test_rtos.py          RTOS object read/write and validation
│   ├── test_middleware.py    Middleware integration
│   └── test_standalone.py    Points the install path at a nonexistent location to verify standalone mode
├── tools/                    Forensic and build scripts (not runtime dependencies)
├── docs/                     Reverse-engineering and usage documentation
├── analysis/                 Machine-readable reverse-engineering artifacts (generated locally, not published)
├── LICENSE  CONTRIBUTING.md  CHANGELOG.md  pyproject.toml
└── .github/workflows/ci.yml  lint + tests + compliance + packaging
```

## 8. Testing

```bat
python -m pytest tests -q          :: Unit tests (no CubeMX needed)
python tests\test_standalone.py    :: Standalone mode: points MXMCP_CUBEMX_ROOT at a nonexistent directory
python tests\test_e2e.py           :: ~70 s, full MCP flow (requires CubeMX)
python tests\test_advanced.py      :: 60+ assertions, covering the newly added command families
python tests\test_rtos.py          :: RTOS object create/delete/update and unique-name constraint
python tests\test_middleware.py    :: Middleware enablement and active IP report
python tools\check_compliance.py   :: Confirms no ST-derived files have entered the repository
```

Measured results (2026-10-29, Windows + CubeMX 6.15.0):

| Script | Result |
|---|---|
| `test_units.py` | Passed (including real generation of 913 files) |
| `test_e2e.py` | Passed (F1 full flow, board project, F4 clock, CLI bridge) |
| `test_advanced.py` | **ALL OK** (as of the 93-tool version) |
| `test_rtos.py` | Passed (tasks/queues/semaphores + duplicate-name rejection) |
| `test_middleware.py` | Passed (FREERTOS integration + verify) |
| `test_standalone.py` | Passed (no installation: create project → pins → generate 6 files) |

## 9. License

MIT (see [LICENSE](LICENSE)). **Note**: the repository contains no ST-derived data —
the data pack and decompiled artifacts are generated locally by users from their own installation (`python -m mxmcp.bundle build`),
and are not distributed with the repository or releases. See [docs/OPEN_SOURCE.md](docs/OPEN_SOURCE.md) for details.
STM32 / STM32CubeMX are trademarks of STMicroelectronics; this project is not affiliated with them.
