# Feature Coverage Matrix — All CubeMX Capabilities → CLI → MCP Tools

This table is the acceptance checklist for "fully reverse-engineering all features": every row is a feature that really exists in CubeMX,
and each one has an entry point in MCP. It is based on `analysis/cli_registry.json` (267 registrations),
`analysis/cli_usage_tables.txt` (runtime usage tables), `analysis/api_index.json`
(3 222 classes / 41 841 methods) and `analysis/plugin_protocol.json` (217 opcodes).

Column meanings:
- **CLI**: the official command that drives it (the `cli` tool can execute any of them verbatim)
- **MCP**: the wrapped tool (if "—", only the `cli` fallback is available)
- **Offline**: ✅ = works without CubeMX installed (uses the bundled data pack / standalone engine); ❌ = requires the official engine

---

## 1. Home Page / MCU Selection

| Feature | CLI | MCP | Offline |
|---|---|---|---|
| Search by family/part number | — (GUI selector) | `mcu_search` `family_list` `family_mcus` `mcu_info` | ✅ |
| Reverse lookup of pin functions | `get functions <pin>` | `mcu_pin_functions` `pin_functions` | ✅ |
| Board list/search | `loadboard` | `board_list` `board_search` `project_load_board` | ✅ |
| Parametric selection (commercial database) | — | `product_db` (read-only SQLite, 19 tables / 17k CPNs) | ✅ |
| Cross-selection/alternative parts | — | `product_db` + `catalog_index` | ✅ |
| Table-driven selector | `selector list mcus` `selector set peripheral` | `selectors` | ❌ (requires GUI dialog) |
| Example project selection | `exampleselector list examples` … | `selectors` | ❌ |

## 2. Pinout & Configuration

| Feature | CLI | MCP | Offline |
|---|---|---|---|
| Pin list/current mapping | `get pinout` | `pinout_get` | ✅ |
| Assign/reset/clear/lock/reserve | `set pin` `reset pin` `clearpinout` `lock pin` `set pinreservation` | `pin_set` `pin_reset` `pin_clear_all` `pin_lock` `pin_reserve` | ✅ (`standalone_pin`) |
| Available signals for a single pin | `get functions` | `pin_functions` `standalone_signals` | ✅ |
| Peripheral list | `get mcu peripherals` | `peripheral_list` `mcu_info` | ✅ |
| Mode list (all/available/mapped) | `get modes` `get available modes` `get mapped modes` | `mode_list` `mode_catalog` | ✅ (`mode_catalog` uses db) |
| Enable/disable/check mode | `set mode` `reset mode` `check mode enabled` | `mode_set` `mode_reset` `mode_check` `standalone_mode` | ✅ |
| Sub-mode tree | `get sub-modes` `get sub-mode-state` | `sub_modes` `submode_state` | ❌ |
| Parameter read/write/batch/refresh | `get/set ip parameters` `IPParameters` | `ip_param_get` `ip_param_set` `ip_params_set` `ip_params_dump` | ✅ (`standalone_param`) |
| Value domains and constraints | `get mode_param_possvalue` `get mode_param_pattern` | `clock_param_possible_values` `mode_pattern` `value_check` | ✅ (`value_check` requires engine) |
| GPIO parameters (label/pull-up/pull-down/speed) | `set gpio parameters` | `gpio_params` `gpio_set` | ✅ |
| NVIC (15 verbs) | `NVIC enable/disable/get_*/set_*` | `nvic_read` `nvic_write` `standalone_nvic` | ✅ (standalone engine stores NVIC.<IRQ>) |
| DMA requests/streams/parameters | `dma list_all/list/available_*/is_available/add/delete/set_flow/set_param` | `dma_query` `dma_mutate` | ❌ |
| MDMA channels/requests | `mdma list_*/add_*/delete_*` | `mdma_query` `mdma_mutate` | ❌ |
| GIC (MP1/MP2 interrupt controller) | `gic get_*/enable/disable/set_triggering_mode` | `gic_query` `gic_mutate` | ❌ |
| Middleware integration | `set mode <MW> <mode>` `add mw` | `middleware_list` `middleware_add` | Partial (list ✅) |
| RTOS objects (tasks/queues/semaphores…) | — (GUI data editor) | `rtos_schema` `rtos_status` `rtos_objects` `rtos_object_write` `rtos_config` | ✅ (writes .ioc + engine reload) |
| Clock tree | `clock resolution` | `clock_get` `clock_set` `clock_resolve` | ❌ (solving requires engine) |
| Power consumption calculation | — (power plugin, 225 models) | — (data extracted, see `analysis/subsystem_contracts.json`) | ✅ |
| Constraint import | `import GPIOconstraint` `import channelconstraint` | `porting` | ❌ |

## 3. Project Manager

| Feature | CLI | MCP | Offline |
|---|---|---|---|
| New/open/save/save as/delete | `load` `config load/saveas/saveext` | `project_create` `project_open` `project_save` `project_save_as` `project_delete` `standalone_create` `standalone_open` | ✅ (standalone) |
| Load MCU / board | `load` `loadboard` `tinyload` | `project_load_mcu` `project_load_board` | ✅ (project creation)/❌ (loadboard) |
| Project options (toolchain/heap & stack/file layout) | `project toolchain/compiler/path/name/…` | `project_options` `project_set_option` | ✅ (stored in .ioc) |
| Code generation | `project generate` `generate code` | `project_generate` `generate_code` `standalone_generate` | ✅ (`standalone_generate`) |
| Generated content inspection | — | `project_files` `verify` `standalone_validate` | ✅ |
| Report / CSV / script export | `csv pinout` `export script` | `project_report` `project_csv` `project_export_script` | ✅ |
| Compare two projects | `cpload project1/2` `cpexport` | `ioc_compare` `project_diff` | ✅ (`project_diff`) |
| Import configuration (port to another MCU) | `import openioc/config/try auto import/add_compatibility_rule` | `porting` | ❌ |
| Toolchain integration | `simulate cubeIDE` | `ide_bridge` | ❌ |

## 4. Tools

| Feature | CLI | MCP | Offline |
|---|---|---|---|
| Memory map (MMT, H5/H7RS/N6) | `MMT dump/reserved/resetReserved/load-save pre-config/ThreadX` | `mmt` | ❌ |
| LPBAM multi-context | `MultiConfig get/add/delete/rename/select LPBAMConfiguration` | `lpbam` | ❌ |
| Database refresh | `swmgr refresh/install/remove/set repository` | `swmgr` | ❌ |
| Product database query | — | `product_db` | ✅ |
| Copyright/license files | — | `analysis/strings_report.json`, `docs/SECURITY_NETWORK.md` | ✅ |

## 5. Software Packages / Library Management

| Feature | CLI | MCP | Offline |
|---|---|---|---|
| Firmware package status | `swmgr` `get <IP> …` | `firmware_packages` (local repository scan + integrity criteria) | ✅ (scan) |
| CMSIS-Pack components | `pack status/enable/disable/validate/context/migrate` | `pack_status` `pack_enable` `pack_disable` `pack_validate` | ❌ |
| X-CUBE download | `xcubedl` | `xcubedl` | ❌ |
| Login/logout | `login` `logout` `login_with_gui` | `login` `logout` | ❌ |
| Template library | — | `template_list` `ip_library` | ✅ |

## 6. `.ioc` and Protocol Layer

| Feature | CLI | MCP | Offline |
|---|---|---|---|
| Read/write/delete arbitrary keys | — | `ioc_get` `ioc_set` `ioc_delete` `ioc_import` `ioc_export` | ✅ |
| Full state view | `get pinout` + file read | `standalone_view` | ✅ |
| Command registry | `help` | `command_catalog` (267 entries, incl. registering class/arity/help) | ✅ |
| Arbitrary CLI execution | — | `cli` `cli_batch` `cli_help` | ❌ |
| Engine runtime properties/log level | `getprop` `setprop` `getenv` `log` | `runtime_props` | ❌ |
| Consistency checks | `check mcu modes` `xts` `xtest` `pinout check keep user placement` | `compliance` | ❌ |

## 7. Standalone (No-Install) Capabilities

The `standalone_*` family + all ✅ tools depend only on `mxmcp/data/cubemx-db.zip`
(9.1 MB: 2 019 MCUs / 245 083 pins / 138 565 IP entries / 274 IP mode sets /
215 boards / 1 756 template manifests / HAL Init parameter tree).
See [STANDALONE.md](STANDALONE.md) for details.

---

## 8. Parts That Explicitly Cannot Be Reproduced Without an Installation (Honest Boundaries)

| Capability | Reason | Alternative |
|---|---|---|
| Clock tree solving | The solver is a proprietary algorithm in `clock.jar` (4 entry paths + constraint propagation) | Supply `RCC.*` parameters manually, or install CubeMX and use `clock_set` |
| Original ST code generation | 1 756 FreeMarker templates + per-IP product logic | `standalone_generate` produces a compilable skeleton, with fields taken from the .ioc |
| Firmware package download/install | Requires my.st.com login + the official updater protocol | `firmware_packages` scans locally, or use `swmgr` |
| Pack component enabling | Depends on `TP_ADVANCED_MODE` and the official pack index | `product_db` + `middleware_list` provide equivalent information |
| GUI selectors/wizards | Commands are only registered after the dialog is instantiated | Offline catalog tools cover the same data |
| Power/LPBAM/DDR calculations | Calculations live inside plugin jars; the data can be extracted but the algorithms have not been rewritten | See data in `analysis/subsystem_contracts.json` |
