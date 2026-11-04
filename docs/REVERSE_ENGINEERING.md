# STM32CubeMX 6.15.0 — Reverse Engineering Notes (final version, including full CLI testing)

Target: `C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX` (v6.15.0, DB.6.0.150)
Deliverable: `mxmcp` — an MCP server that retains all of CubeMX's capabilities (MCU selection/pins/clocks/peripherals/middleware/project generation/package management/code export).

---

## 1. Installation Layout and Runtime Mechanism

```
STM32CubeMX/
├── STM32CubeMX.exe        227 MB, PE32+ SFX: stub + embedded ZIP (same contents as the jar)
├── STM32CubeMX.l4j.ini    Launcher parameters (trustStoreType=WINDOWS-ROOT, etc.)
├── jre/                   Temurin 21.0.3 (includes javac/javap/jlink; not a jlink-trimmed build)
├── db/                    MCU/board/IP database (XML + FTL templates + images)
├── plugins/               19 feature plugin jars + ip/*.jar (45 IP UI plugins)
├── olddb/  help/  utilities/  Uninstaller/
└── .installationinformation   IzPack install metadata (includes Jenkins build path, DB version, APP_VER=6.15.0)
```

Key conclusions:

* **It is neither Excelsior JET nor native-image**. The EXE is a PE stub + a complete Java application container:
  `java -jar STM32CubeMX.exe` runs it directly (UM1718 documents this as well), so no unpacking is needed;
  **the plugin jars and the main application classes are all plaintext** and can be `javap`'d/decompiled directly.
* On first run, `java -jar` looks for the embedded ZIP inside the EXE; that ZIP's central directory has been truncated/rewritten
  (the first few records have a name-length 1 byte shorter than actual, size/CRC zeroed, EOCD truncated),
  but **the local file headers are intact**. `tools/dump_exe_zip.py` uses streaming local-header parsing to rebuild
  `_extract/cubemx_app.jar` (12 666 entries, of which 242 classes are under `com/st/microxplorer/**`).
* The main application depends on `com.st.components.*` (CommandLineManager / ApplicationProperties, etc.);
  these classes are **not in the embedded jar**: the startup log shows they are provided at runtime by the EXE bootstrap layer
  (`java -jar` can still resolve them, meaning they live in a non-ZIP region of the EXE / the bootstrap classpath).
  Impact: the CommandLineManager source cannot be read statically from the jar, so we switched to **runtime behavior capture** (see §3).
* Log: `%USERPROFILE%/.stm32cubemx/STM32CubeMX.log`, and the log4j2 configuration
  `log4j/log4j2.stm32cubemx.xml` also outputs to stdout — this is the capture channel for the CLI.
* User directories: `~/.stm32cubemx/` (preferences, third-party pdsc, log4j config), `~/.stmcufinder/`,
  `~/STM32Cube/Repository/` (firmware packages; this machine has `STM32Cube_FW_F1_V1.8.0` and several X-CUBE pdsc installed).

## 2. Feature Surface (must be preserved 1:1)

| Area | Implementation |
|---|---|
| MCU selection / pin multiplexing / conflict checking | `db/mcu/*.xml` (5 960 files) + main app `mc/mcu` package + `ip/*.jar` |
| Clock tree | `plugins/clock.jar` + `db/mcu/config/RCC-*_Configs.xml` |
| Peripheral and middleware configuration | `plugins/ip/*.jar`, `db/mcu/IP/*_Cube_Modes.xml` |
| Project generation (C code + IDE projects) | `plugins/projectmanager.jar`, `filemanager.jar`, `db/templates/*.ftl` (Freemarker) |
| Software package management (Cube FW / CMSIS-Pack) | `plugins/updater.jar`, `thirdparty.jar`, `db/plugins/updater/*.xml` |
| Board support | `db/plugins/boardmanager`, `loadboard` command |
| Power calculation / LPBAM / DDR / RIF / CAD | `power.jar`, `lpbam.jar`, `ddr.jar`, `rif.jar`, `cadmodel.jar` |
| Custom template generation | `set tpl_path`/`dest_path` + GraalJS (the jar contains truffle/js; `-s` script mode uses it for execution) |

**Conclusion: do not rewrite the engine.** The MCP acts as a **controlled front end** driving the official engine (`java -jar STM32CubeMX.exe -q <script>`);
all capabilities are executed through CubeMX's own command language, so fidelity is inherent (pin validity, clock solving and code templates are all handled by the ST engine).

## 3. CLI Command Language (evidence gathered at runtime)

Three modes:

* `-i`: interactive `MX>` prompt
* `-s <file>`: run a script with the UI
* `-q <file>`: run a script without the UI (headless) ← the mode used by the MCP (there is also `-expMode`, which skips the splash screen)

Command families (output of `help`; all are top-level commands; subcommands are space-separated):

```
help exit script exit_mx set get reset add check csv generate list import export
lock unset pinout disable load loadboard tinyload waitclock switch
project setDriver SetStructure SetCopyLibrary config swmgr pack dma NVIC clock
cpload cpexport login logout login_with_gui updateIpUI tooltip simulate
isPluginError user_analytics log setprop getprop getenv xcopy xts xtest xbuild
popupwrapper xcubedl MultiConfig ocxtest possible_value not_a_possible_value
```

### 3.1 Core Semantics Confirmed by Testing

| Command | Semantics | Notes |
|---|---|---|
| `load <mcu>` | Create a new project for this MCU (clears the current configuration) | `load STM32F103C8Tx` |
| `config load <ioc>` | Load an .ioc | After loading, `get mcu name` returns the normalized name `STM32F103C(8-B)Tx` |
| `config saveas <name>` | Save as a new project | **Actually writes to `<project path>/<basename>/<basename>.ioc`**; writes to `%CD%` if `project path` is not set |
| `config save` | Save the current project | **Hangs (no output)** when pointing to an uninitialized path; must not be used blindly in headless mode |
| `config saveext` | Save the full configuration including default values | |
| `project path/name/toolchain` | Project generation target | `project path` immediately creates `Untitled/Untitled.ioc` |
| `project generate` | Generate the full project (including firmware libraries and IDE project) | Tested: produced Core/Drivers/MDK-ARM etc. in 21 s |
| `generate code <dir>` | Generate only the MX code (no libraries/IDE project) | |
| `generate all_code_in_main` / `one_file_per_ip` | Generation layout | Equivalent to `project couplefilesbyip 0/1` |
| `set pin <pin> <signal>` | Assign a pin function | Signal names come from `get functions <pin>` (e.g. `USART1_TX`, `RCC_OSC_IN`) |
| `set mode <IP> "<Mode>"` | Set the peripheral mode | Mode names come from `get modes <IP>`; **must be quoted** to work reliably |
| `set ip parameters <IP> <param> <value>` | Set an IP parameter | Arbitrary key names using `.` can also be written (see below) |
| `set ip parameters <IP> IPParameters a,b,c` | **Register parameters in the .ioc `IPParameters` list** | Key trick: unregistered parameters stay only in memory and are not persisted |
| `get ip parameters <IP> <param>` | Read back | Returns `=null` / `is not set` when unregistered |
| `get functions <pin>` / `get pinout` / `get signal <pin>` | Pin/function queries | `get pinout` outputs `pin: signal` |
| `get modes/mapped/available/mode/...` | Peripheral mode queries | |
| `set gpio parameters <pin> <param> <value>` | GPIO parameters | **pin must be the full name** (`PC13-TAMPER-RTC`); `PC13` returns KO |
| `reset pin/signal/mode/...`, `lock pin`, `clearpinout` | Undo and locking | |
| `check mode enabled <IP> "<Mode>"` / `check mcu modes` | Validity checks | |
| `NVIC enable|disable|set_priority|set_subpriority|set_prioritygroup` | Interrupt configuration | Obtained from `export script` recordings |
| `export script <file>` | **Serialize the current configuration into a replayable CLI script** | Reverse-engineering shortcut: any .ioc can be turned into a command sequence |
| `csv pinout <file>` | Pin table export | |
| `loadboard <board> <allmodes|nomode>` | Board project | |
| `swmgr refresh|install|remove|set repository|connection status` | Firmware package management | |
| `pack enable|disable|status|validate|context|migrate` | CMSIS-Pack components | |
| `project compiler GCC|Starm-Clang`, `SetStructure Advanced|Basic`, `SetCopyLibrary ...` | Project options | |
| `setprop/getprop/getenv`, `login/logout`, `simulate cubeIDE`, `MultiConfig ...`, `xcubedl`, `xcopy`, `xbuild` | Other capabilities | |

### 3.2 Evidence-Gathering Methods

* `tools/run_cmds.py`: feeds command lines to `-q`, captures stdout (cube's log4j stdout channel),
  and filters out `[INFO]` lines to get the pure CLI responses (`OK`/`KO`/data).
* `tools/collect_help.py`: runs `<cmd>`/`help <cmd>` for each command family and saves the output to `docs/cli_help/*.txt`.
* `tools/dump_all_commands.py`: performs an `addCommand` constant-pool scan + `javap`
  decompilation on all classes in `plugins/**`, extracting 89 registration strings (including hidden families such as `pack enable`, `NVIC`, `clock resolution`, `dpm`).
* `tools/mx_harness.py`: minimal Python-side driver (prototype of the MCP session engine).

### 3.3 Key Pitfalls (resolved)

1. **`config save` hangs in headless mode** → use only `config saveas`, and set `project path` beforehand.
2. **`-q` mode still initializes Swing/JxBrowser** → each launch takes about 6–17 s; the MCP must keep a persistent session
   (the stdin/stdout channel of interactive `-i`); one-shot cold starts are too slow.
3. **Unregistered parameters are not persisted** → see the `IPParameters` trick; this also solves the clock tree: RCC's
   `AHBFreq_Value/PLLMUL/SYSCLKSource/APB1CLKDivider/...` can all be verified from the `.ioc`.
4. **Output directory semantics**: `config saveas`/project generation are both relative to `project path`; the MCP must force absolute paths and return the real path.
5. **The `.ioc` is the single authoritative state**: `config saveext` + `IPParameters` persist the in-memory state completely,
   so the MCP's "read state" should read the `.ioc`, and "modify state" goes through the CLI + re-save; the two can cross-check each other.

## 4. Database Resources (for offline query tools)

* `db/mcu/*.xml`: one file per MCU (pins, packages, IP instances, reset state, alternate-function mapping)
* `db/mcu/families.xml`, `rules.xml`, `compatibility.xml`, `defines/defines`
* `db/mcu/IP/*_Cube_Modes.xml`: IP mode trees; `db/mcu/config/*_Configs.xml`: mode/parameter/clock constraints
* `db/plugins/boardmanager`, `db/plugins/mcufinder/mcu/cube-finder-db.zip` (42 MB MCU selection database)
* `db/templates/*.ftl` (Freemarker code templates, about 700), `db/plugins/projectmanager/*.ftl` (project file templates)
* `db/plugins/power/*.xml|json` (power models and RF/SubGHz scenarios)

## 5. Deliverables

```
mxmcp/
├── mxmcp/
│   ├── server.py        MCP entry point (stdio JSON-RPC 2.0; --selftest/--call/--list-tools)
│   ├── rpc.py           Protocol layer (initialize / tools/list / tools/call / resources)
│   ├── engine.py        Engine (persistent -i session; kills process on timeout; strips prompt-merged lines)
│   ├── store.py         Project pool, save/reload, MCU part number → RefName resolution, firmware paths
│   ├── ioc.py           .ioc read/write, IPParameters view, structural diff
│   ├── catalog.py       Local db index (2016 MCUs / 215 boards / 687 IP modes / 656 templates)
│   ├── firmware.py      Firmware package integrity scan (package.xml + Drivers)
│   └── tools_*.py       Project / selection / pins & peripherals / clock / generation / software packages / CLI fallback
├── tests/               test_units.py (20 assertions) + test_e2e.py (full MCP flow)
├── docs/                This file, CLI_REFERENCE.md, VALIDATION.md, cli_commands.tsv, javap dumps
└── tools/               Reverse-engineering and probe scripts (reproduce the evidence; not runtime dependencies)
```

## 6. Phase 2 Corrections (early assumptions overturned by testing)

| Early assumption | Correction from testing |
|---|---|
| `set gpio parameters <pin>` is unusable; only direct `.ioc` writes work | **Usable**: pin must be the full MCU name (`PC13-TAMPER-RTC`); only the short name `PC13` returns KO |
| `pack enable` is just a syntax issue | Requires `TP_ADVANCED_MODE=on` + an already-downloaded third-party pack; the built-in peripheral pack is in the `isIntegrated()==true` state and can never be selected |
| `project generate` is slow/unstable | As long as the firmware package version matches the `.ioc`'s `FirmwarePackage`, it is stable at 5 s; a mismatch triggers an online download (hangs without UI) |
| Clock tree writes take effect in one pass | On a new project, the first write only registers parameters; derived values update only after save + reload and a second write pass (F1); an already-solved project needs only one pass |
| `-q` batch mode is sufficient | `-q` cold-starts in 6–17 s each time, and some commands pop up dialogs/hang going online; a persistent `-i` + timeout restart is required |


