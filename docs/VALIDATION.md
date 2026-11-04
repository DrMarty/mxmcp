# Acceptance Record (final)

Environment: Windows 10 · Python 3.11 · STM32CubeMX **6.15.0 / DB.6.0.150** · no third-party runtime dependencies
Deliverable: `mxmcp` **113 MCP tools**, dual mode (hybrid drives the official engine / standalone needs zero installation)

---

## 1. Reverse-engineering evidence ledger

| # | Finding | Evidence artifact | Count |
|---|---|---|---|
| 1 | The deliverable is a Java application packaged as a PE32 loader + embedded ZIP; no unpacking needed | `analysis/cd_entries.json`, `analysis/stub_version.json`, REA PE results | local headers start at `0x13000`, CD at `0xD2F0A03` |
| 2 | **All** 54 774 entries of the embedded archive can be rebuilt (0 failures) | `tools/rebuild_full_jar.py` → `_extract/cubemx_full.jar` | 227 113 372 B |
| 3 | `com/st/components/**` is inside the archive (including `CommandLineManager`) | `docs/javap/`, `analysis/api_index.json` | 196 entries |
| 4 | Full table of classes/methods/fields | `analysis/api_index.json` | **3 222 classes / 41 841 methods / 38 255 fields / 339 packages** |
| 5 | CLI registry | `analysis/cli_registry.json`, `docs/CLI_REGISTRY.md` | **267 entries / 64 command heads / 14 jars** |
| 6 | Runtime usage tables (including echo of read-only commands) | `analysis/cli_usage_tables.txt`, `docs/cli_usage_tables.txt` | 34 command families |
| 7 | Plugin RPC protocol | `analysis/plugin_protocol.json` | **217 opcodes + 30 return codes + 99 constants** |
| 8 | Data model (6 690 XML files) | `analysis/db_schema.json`, `analysis/db_census.json` | 171 directories / 2 019 MCUs / 1 321 IP Modes / 1 308 Configs |
| 9 | Condition expression language | `analysis/condition_language.json` | **636 975** expressions |
| 10 | `.ioc` grammar | `analysis/ioc_grammar.json` | 506 corpus files → **7 670** key patterns |
| 11 | Code generation model | `analysis/template_model.json`, `analysis/config_model.json` | **1 756** templates / **2 706** model keys / 192 IP parameter trees |
| 12 | IDE generation backend | `analysis/cubeide_services.json` | 20 p2 plugins / 28 services / mxScratch schema |
| 13 | RTOS object model and storage | `analysis/rtos_model.json`, `docs/rtos_apis.xml` | v1 7 classes / v2 8 classes / 75 fields |
| 14 | Middleware directory | `analysis/middleware_constants.json` | **239 constants / 36 instance names** |
| 15 | Trust chain and endpoints | `analysis/strings_report.json`, `docs/SECURITY_NETWORK.md` | 5 certificates / 1560 URLs / 460 hosts |
| 16 | Full installation tree | `analysis/install_census.json`, `analysis/peripherals_of_install.json` | 11 378 files / 1 520 MB / 709 directories |
| 17 | Remaining subsystems | `analysis/subsystem_contracts.json`, `analysis/plugin_resources.json` | power 225 / clock 64 / RIF 70 / PackCreator 4 823 classes |
| 18 | Product selection database | `analysis/mcufinder_data_layer.json` | 19 tables / 17 491 CPNs / 644 828 attribute rows |

## 2. Tool surface

```
python -m mxmcp.server --list-tools   ->  113 tools
python -m mxmcp.server --selftest     ->  {"name":"mxmcp","version":"1.1.0"} / tools: 113
```

| Family | Count | Key tools |
|---|---|---|
| Project | 18 | `project_create/generate/save/diff/report/export_script` |
| Selection (offline) | 15 | `mcu_search/mcu_info/mcu_pin_functions/board_*/mode_catalog/product_db/command_catalog` |
| Pins & peripherals | 22 | `pin_set/pin_functions/gpio_*/mode_*/ip_param_*/value_check/submode_state` |
| Interrupts · DMA · memory | 10 | `nvic_read/write/dma_*/mdma_*/gic_*/mmt/lpbam` |
| RTOS · middleware | 7 | `rtos_schema/status/objects/object_write/config/middleware_list/add` |
| Clock | 4 | `clock_get/set/resolve/param_possible_values` |
| Generation · validation | 4 | `project_generate/generate_code/verify/compliance` |
| Porting · comparison | 3 | `porting/ioc_compare/selectors` |
| Software packs | 8 | `pack_*/swmgr/xcubedl/login/logout` |
| **Standalone mode** | **12** | `standalone_info/create/open/pin/signals/mode/param/nvic/view/validate/generate/mcu` |
| `.ioc` · fallback | 10 | `ioc_*/cli/cli_batch/cli_help/runtime_props/ide_bridge` |

## 3. Test results

| Script | Needs CubeMX | Result |
|---|---|---|
| `pytest tests/test_smoke.py` | No | **12 passed** (protocol, `.ioc`, data pack, standalone engine, code generation, IP modes, compliance statement) |
| `tests/test_standalone.py` | **No** | **Passed**: without an installation, create project → pin validation → mode → parameters → NVIC → generate 6 files; invalid signal rejected, engine tools fail immediately |
| `tests/test_units.py` | Yes | Passed (including real generation of 913 files) |
| `tests/test_e2e.py` | Yes | Passed (F1 full flow / boards / F4 clock / CLI bridge) |
| `tests/test_advanced.py` | Yes | **ALL OK** (dma/nvic/gic/mmt/porting/selectors/catalog all green) |
| `tests/test_rtos.py` | Yes | Passed (task/queue/semaphore create/delete/update + duplicate-name rejection + config) |
| `tests/test_middleware.py` | Yes | Passed (FREERTOS integration → active IP report → verify) |

Static checks:

```
ruff check mxmcp tests        ->  All checks passed!
python -m mxmcp.bundle verify ->  2028/2028 members ok, mcus: 2019
```

## 4. Standalone mode test run (`MXMCP_CUBEMX_ROOT` pointing to a nonexistent directory)

```
tools: 113
mode: standalone | engine: False | pack: True 9107807
counts: {'mcu': 2019, 'pins': 245083, 'ips': 138565, 'families': 27,
         'boards': 215, 'ip_modes': 274}
search: 1 ['STM32F103C(8-B)Tx']
create: STM32F103C(8-B)Tx LQFP48 pins: 44
PA9 signals: ['TIM1_CH2','USART1_TX','GPIO_Input','GPIO_Output','GPIO_ANALOG','GPIO_EVENTOUT']
pin: USART1_TX / USART1_RX / GPIO_Output
invalid pin signal rejected: True
mode/param/nvic: OK
validate ok: True []
generate: 6 files standalone
main.c contains BaudRate = 115200: True
engine tool without install -> clean error: True
```

## 5. Key behaviors (all hardened into code paths)

1. `load` only accepts a db RefName; part numbers are resolved first (otherwise the interpreter hangs forever).
2. Parameters are only written to disk once registered in `<IP>.IPParameters`.
3. `config save` without a path hangs → only `saveas`/`saveext` are used.
4. Three response framings: standalone terminator line / terminator glued to a line (`…0 OK`) / log4j lines (dma, nvic,
   `get mode_param_pattern`) — `engine.py` handles all of them.
5. On engine timeout the process is killed, and the next call automatically restores state via `config load`; the result contains `hung: true`.
6. A firmware package version mismatch triggers an online download (which hangs without a UI) → pre-check before generation + automatic version pinning.
7. RTOS tables only appear in `project_ext.ioc` → merged view on read; normalized via engine reload after write.
8. Middleware IPs need an unquoted `set mode`, and `get modes` returns KO → fall back to the db mode table.
9. Without an installation, engine tools return an actionable error **immediately** and point to `standalone_*`.

## 6. Known limits (things we don't pretend to do)

| Item | Reason | Status |
|---|---|---|
| Clock tree solving | Proprietary algorithm in `clock.jar` | hybrid only; standalone keeps `RCC.*` parameters as-is |
| ST's original code | 1 756 FreeMarker templates + product logic | standalone generates a compilable skeleton (`fidelity: standalone`) |
| GUI selectors/wizards | Commands are only registered after the dialog is instantiated | Covered by offline catalogs with the same data |
| Power/LPBAM/DDR calculations | Algorithms inside plugins | Data extracted, algorithms not reimplemented |
| React client module graph | Single-file bundle exceeds the REA worker heap | Bridge interface and endpoints extracted; recorded as not expanded |
| `pack enable` | Requires `TP_ADVANCED_MODE` + a downloaded third-party pack | Kept as an explicit tool; errors are returned faithfully |

## 7. Reproduction

```bat
python -m mxmcp.bundle build && python -m mxmcp.bundle verify
python -m mxmcp.server --selftest
python -m pytest tests\test_smoke.py -q
python tests\test_standalone.py            :: no-installation verification
python tests\test_e2e.py                   :: requires CubeMX
python tools\check_compliance.py           :: pre-commit compliance check
```
