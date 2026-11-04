# STM32CubeMX 6.15.0 — Full Architecture Reverse Engineering

Evidence source: the local installation at `C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX`
(1 137 8 files / 1 520 MB / 709 directories), artifact SHA-256
`67b12576eed1c9544668b529458d87e6a9db600cf53492da1534afa8cf1ca0b8`.
All figures were extracted directly from the installation by `tools/*.py` and REA; `analysis/*.json` holds the raw records.

---

## 0. Layered Overview

```
STM32CubeMX.exe   PE32(i386) Launch4j loader + embedded ZIP (the same file is the jar)
  └─ Embedded ZIP: starts at 0x13000, central directory at 0xD2F0A03, 54 774 entries
       ├─ com/st/components/**        Framework layer: CommandLineManager, pdscmanager, JxBrowserEngine, swing, net
       ├─ com/st/microxplorer/**      Main program: mcu model, codegenerator, db, mcufinder, plugins.*
       ├─ com/st/ipmodeconfigmanager  IP mode/config XML engine (104 classes)
       ├─ org/graalvm|com/oracle/truffle  GraalJS (scripts/validation expressions)
       ├─ com/teamdev/jxbrowser       Chromium engine (unpacked to ~/.jxbrowser-8.5.0 on first run)
       └─ Third-party libraries: poi/xmlbeans, apache ant, jfree, bouncycastle, lowagie(iText), jackson…
  ├─ plugins/*.jar   19 feature plugins (clock/power/projectmanager/thirdparty/analytics…)
  ├─ plugins/ip/*.jar 45 IP configuration plugins (adc/can/i2c/freertos/usbx…)
  ├─ db/             Data assets (XML 6 775 / FTL 1 756 / IOC 504 / LD 277 / DTSI 75…)
  ├─ third_parties_plugins/  STM32CubeIDE-MX-services (Eclipse p2 repository, 20 plugins + 34 features)
  │                          + com.st.stm32cube.ide.common.services.mx.jar-1.19.0-b1.jar (62 MB)
  ├─ utilities/      STM32PackCreator.jar (4 823 classes), TrustedPackageCreator.jar
  └─ Uninstaller/    IzPack uninstaller (uninstaller.jar 1 117 classes)
```

Class/method counts (`analysis/api_index.json`, counting only top-level `com.st.**` classes):
**3 222 classes / 41 841 methods / 38 255 fields / 339 packages**.

| Package | Classes | Methods | Role |
|---|---|---|---|
| `com.st.microxplorer.mcu` | 67 | 3 430 | MCU/IP/pin/interrupt object model, host of CLI commands (Mcu, NVICService, DMAService, MDMAService, GicService, Constraints…) |
| `com.st.microxplorer.codegenerator` | 43 | 1 401 | Main C code generation engine (FreeMarker-driven) |
| `...plugins.projectmanager.gui` | 70 | 1 102 | Project Manager page (toolchain, backup, reports) |
| `com.st.microxplorer.mcufinder.db` | 24 | 1 056 | Selection database (SQLite + cross-selection) |
| `...plugins.projectmanager.model` | 14 | 1 004 | `.ioc` key-value model |
| `...mcu.memorymap` | 32 | 702 | MMT memory mapping tool |
| `...plugins.projectmanager.engine` | 18 | 646 | Generation scheduling (IDE services, file copying) |
| `...plugins.thirdparty.model` | 36 | 630 | CMSIS-Pack/middleware model |
| `com.st.ipmodeconfigmanager.xmlManager.ipconfig` | 22 | 620 | `*_Configs.xml` parsing |
| `...projectmanager.security[.reader]` | 76 | 1 074 | H5/H7RS secure boot/TrustZone/OTFDEC/IOPMP configuration |
| `...plugins.risaf` | 54 | 567 | RISAF resource security isolation |
| `...mcufinder.db.crossselector` | 38 | 505 | Cross-selection (price comparison/alternative parts, Ultralibrarian) |

---

## 1. Native Loader (the EXE itself)

As reported by REA's PE parser (`evidence ev_77654766…`, `ev_cb53c303…`, `ev_18f9bfe0…`):

| Fact | Value |
|---|---|
| Format | **PE32 (i386, machine 332)**, not PE32+; no TLS directory, no LOAD_CONFIG |
| Import table | 5 DLLs / 88 functions, imphash `6011984d7c1f1b97a34d7517a498bff8` |
| Key imports | `RegOpenKeyExA/RegQueryValueExA/RegEnumKeyExA` (locate the JRE), `CreateProcessA` (launch the JVM), `FindResourceExA/LoadResource/LockResource` (read embedded resources), `CreateMutexA/WaitForSingleObject` (single instance), `GlobalMemoryStatusEx` (compute `-Xmx`), `SetEnvironmentVariableA`, `MessageBoxA/CreateWindowExA/LoadImageA/SetTimer` (startup splash), `ShellExecuteA` (open links) |
| Resources | `RT_ICON` in 8 sizes (16/20/24/32/48/64/128 + one variant), `RT_GROUP_ICON`, `RT_VERSION`(772 B), `RT_MANIFEST`(id 24) |
| Version info | FileDescription `MicroXplorer for STM32Cube`, InternalName/ProductName `STM32CubeMX`, **FileVersion/ProductVersion `6.15.0-RC4`**, LegalCopyright `STMicroelectronics`; the stub itself is `0.1.0.4` (Launch4j) |
| Authenticode | Signer **STMicroelectronics International N.V.** (CH, DigiCert Trusted G4 Code Signing RSA4096 SHA384 2021 CA1, serial `0b12c8b575d0d6e16489812ce64cd7c5`, valid 2022-10-26→2025-10-25), with a DigiCert Timestamp 2024 timestamp; the PKCS#7 contains 5 certificates. *Only structurally decoded; the chain and digest coverage were not verified* |

Conclusion: **no packing, nothing to unpack**. `java -jar STM32CubeMX.exe` works directly (the JVM's ZIP reader locates entries via the central directory), and UM1718 documents this as well.

### Actual Structure of the Embedded Archive

| Item | Value | Notes |
|---|---|---|
| Local file header start | `0x13000` (= entry 0's local_header offset 0) | Derived backwards from the local header of `META-INF/MANIFEST.MF` |
| Central directory | `0xD2F0A03`, standard 46-byte records | **The earlier conclusion that "the central directory is truncated/CRCs are zeroed" was wrong**: it was an artifact of misread field offsets (crc@16, csize@20, usize@24, nlen@28) |
| Total entries | **54 774** | The earlier streaming scan only got 12 666, because it stopped at the first byte that did not start with `PK\x03\x04` |
| Full rebuild | `_extract/cubemx_full.jar`, 227 113 372 bytes, `ok=54774 bad=0` | `tools/rebuild_full_jar.py` |
| Composition | truffle 8 138 / jxbrowser 7 185 / icu 5 453 / openxml 3 633 / **microxplorer 3 368** / commons 2 852 / poi 2 769 … | `analysis/cd_entries.json` |

Important correction: **`com/st/components/**` is indeed in the embedded jar (196 entries)**, including
`com.st.components.util.CommandLineManager`. The previous conclusion that it was "provided by the EXE bootstrap layer and cannot be read statically"
came from that incomplete 12 666-entry extraction; it has now been decompiled directly (see §3).

---

## 2. Startup Sequence (verified from logs)

```
Launch4j: find java via registry/environment → assemble -Xmx (GlobalMemoryStatusEx) → CreateProcessA
          java -jar <the exe itself> [-i|-s|-q]
JVM     : load the embedded jar (MANIFEST Class-Path points to plugins/*.jar)
MicroXplorer: select DB (olddb/db → DB.6.0.150) → register 21 plugins
             → MainPanel/TabSelector/ProjectManagerView
             → RtosApiDefinition(rtos_apis.xml) → GPIO constraints/channel constraints
             → updater.jar: register 4 UpdaterGuiPlugins + CMSIS pack repo
             → thirdparty: ThirdParty directory + .stmcufinder/plugins
             → first run: JxBrowser Chromium 134.0.6998.89 unpacked to ~/.jxbrowser-8.5.0
             → McuFinder loads cube-finder-db.db + React client
Cold start takes 15–18 s (same for headless -q/-i)
```

The log level is controlled by `~/.stm32cubemx/log4j2.xml` (`MX_STDOUT` appender + `STM32CubeMX.log`);
`-Dorg.apache.logging.log4j.simplelog.level=TRACE` prints all DEBUG output (used once for forensics;
the config file has since been restored to factory defaults).

---

## 3. CLI Framework (`com.st.components.util.CommandLineManager`)

Decompilation facts:

* Internally maintains a `List<CommandLine>`; `addCommand(String name, String help, int argc, CommandLineListener l)`
  → `addUnique(...)`: `CommandLine(name, help, argc, listener, boolean)`; duplicate names are detected with
  `equalsIgnoreCase` (the first one wins).
* Commands are matched by **whole-string prefix** (case-insensitive), so `get ip parameters RCC BaudRate`
  matches the longest registered string first; argc determines how the remaining arguments are split.
* Interactive protocol: prompt `MX> ` (**no newline**), response terminator `^\s*(\d+)\s+(OK|KO)\s*$`;
  commands with no output leave the prompt stuck to the front of the next response; a few services write their results into **log4j lines**
  (`dma/NVIC/MMT/get mode_param_pattern`), and some write `0 OK` glued directly onto the end of the body text
  — `mxmcp/engine.py` handles all three kinds of framing.
* 89 **root commands**; `help` only prints the global table (`help <cmd>` does not echo subcommands), so subcommand usage has to be
  obtained via the "bare command echo" — which is why `cli`/`cli_batch` must be exposed.
* Dynamic naming: `NVICService.initCommands()` uses
  `getInstanceName()+"<verb>"` (`makeConcatWithConstants`) to register
  `<IP> enable|disable|set_priority|set_subpriority|set_prioritygroup|…`,
  so commands are generated per instance name (NVIC/GIC/DMA…) and the full names are not visible in the static constant pool.

### Complete Registry

`analysis/cli_registry.json` / [docs/CLI_REGISTRY.md](CLI_REGISTRY.md):
**267 unique registrations**, covering 14 jars and 64 command heads. The 89 recorded in the previous version were only the families visible from the main panel.
Newly recorded families (with argc and original help text):

| Family | Count | Representative commands |
|---|---|---|
| `dma` | 18 | `available_controller_streams`, `is_available_in`, `set_flow`, `listbriefly`, `used_flows` |
| `mdma` | 10 | `list_peripheral_requests`, `add_channel_request`, `list_request_channels` |
| `gic` | 7 | `get_enable_state`, `set_triggering_mode`, `set_security` |
| `MMT` | 9 | `dump free|AppReg|HRange|HRegion`, `reserved (HW|SW) "…"`, `load/save pre-config`, `ThreadX y/n` |
| `selector`/`boardselector`/`exampleselector` | 8/7/13 | `list mcus`, `list columns`, `set filter`, `set peripheral <n> <v>` |
| `import` | 10 | `try auto import`, `get report`, `add compatibility_rule`, `set manual import_option`, `hackmxdb` |
| `MultiConfig` | 6 | Add/remove/modify/select LPBAM contexts |
| `cpload`/`cpexport` | 3 | Compare two `.ioc` files side by side and export a report |
| Other | `possible_value/not_a_possible_value ip parameters`, `get sub-mode(s|-state)`, `get mode_param_pattern`, `bootpath wizard`, `generate deviceTree`, `add mw`, `xts/xtest/xbuild/xcopy`, `tooltip log on/off`, `updateIpUI`, `isPluginError`, `simulate cubeIDE`, `user_analytics` |

---

## 4. Plugin Contract

`com.st.microxplorer.plugin.PluginView` (abstract class, implements `IPluginView`+`PluginViewConstants`):

* Lifecycle: `setParent/setUserPreferencesHandler/setApplicationInformation/setTabIndex`
  → `activatePlugin/deactivatePlugin` → `loadConfig(String)/saveConfig(String)`
  → `importConfig` → `exit`.
* UI injection: `addToToolBar(IPluginToolBar)`, `addToMenuBar(IPluginMenuBar)`,
  `addToOutputTab(JTabbedPane)`, `getUI()`, `isVisible()`, `resize()`,
  `skipToError(String)`, `getTooltipText()`.
* Reports: `generatePdfReport(com.lowagie.text.Document, int)`,
  `generateTextReport(PrintWriter)`.
* **Generation**: `HashMap<String, HashMap<String,String>> generateCode(String, IProgressBarMonitor)`
  + `setSpecificCodeInputs()`.
* **RPC**: `Object getSpecificTask(int opcode, Object payload)`.
  `PluginViewConstants` provides **217 opcodes + 30 return codes + 99 string constants**
  (`analysis/plugin_protocol.json`), grouped by subsystem:
  `ANALYTICS(16)`, `FileManager(23)`, `Pinout(13)`, `ProjectManager(41)`,
  `Updater(51)`, `ThirdParty*(dozens)`, `IPManager(5)`, `Clock(1)`, `PCC(2)`…
  The Updater return code table (`ReturnFound/ReturnBusy/ReturnErrorBadMD5/…`) is
  the error enum of the download state machine; `swmgr install` failure messages come directly from it.
* Host interfaces: `IPluginApplicationInformation` (version/icons/debug/DB accessor),
  `IPluginMainPanel` (isMcuLoaded/isModified/showPluginView/printMessage/setPluginError…),
  `IPluginUserPreferences` (login, proxy, repository path, data refresh policy),
  `IPluginDBAccessor` (old/new DB paths and versions), `IPluginMenuBar/RibbonBar/ToolBar`,
  `IPluginColorsManager`.
* 19 feature plugins + 45 IP plugins; IP plugins work through
  an `IPPluginView` subclass inside `ip/*.jar` together with `db/mcu/IP/*_Cube_Modes.xml`.

---

## 5. Code Generation Pipeline

1. `CodeGenerator` (43 classes / 1 401 methods) collects the `generateCode` results of each IP
   (maps categorized as `include/init/deinit/MSP/callbacks`).
2. FreeMarker: **1 756 `.ftl` files** in the installation
   (`db/templates` 1 733 + `db/plugins/projectmanager` 20 + PackCreator 3).
   `analysis/template_model.json` extracts **2 706 model keys**, interpolation counts,
   the include graph and per-template key distribution; high-frequency keys include
   `definition / argument / characteristic / used_api / method / instanceIndex /
   IpInstance / ipName / FamilyName / Configuration / clock / BoardName / filesName /
   fwVersion / SERVICE_SHORT_NAME_UpperCase / SvcNbr`.
3. Naming conventions are visible in template references: `tpl_makefile_v1-0.ftl`, `tpl_dts-v1_kernel_v1-0_dts.ftl`,
   `*_c.ftl` / `*_h.ftl` (paired .c/.h templates).
4. IDE projects (STM32CubeIDE / Makefile / CMake) are produced by **CubeIDE-MX-services**:
   CubeMX first writes **mxScratch** (schema `mxScratch_v30.xsd`, whose root element contains
   `startup / sourceEntries / optimization / memory / memories / lib / include / icfloc …`),
   then invokes services from the p2 pool within the same JVM via `--service <name>`:
   `check / cleanup / projectSetup / projectUpdate / buildSetup / buildUpdate /
   updateScopeFinder / resourcesSetup / startupSetup / lnkSetup / lnkUpdate /
   dtSetup / threadSafeSetup / threadSafeUpdate / debugSetup / debugUpdate /
   projectRootModeSetup` (`analysis/cubeide_services.json`, 28 service classes, 6 message bundles).
   Linker scripts come from the `linkerdb`/`linker` plugins (277 `.ld` files in the installation),
   and device trees come from `dtSetup` + 75 `.dtsi`/59 `.dts` files in `db`.
5. Linker/toolchain: `com.st.stm32cube.ide.*` invokes native tools via `com.sun.jna` (in the p2 pool).

---

## 6. Data Assets (`db/`)

`analysis/db_schema.json` + `analysis/db_census.json` (171 directories):

| Asset | Count | Structural highlights |
|---|---|---|
| `db/mcu/*.xml` | 2 019 | Root `Mcu`: `RefName/Name/PackageName/RPN/Visible/ClockTree/DBVersion/Family`; child elements `Core/Flash/Ram/IONb/Frequency/Voltage/Temperature/Current/E2prom/Peripheral/Signal/IP/Pin`. `Peripheral@Type/MaxOccurs`, `IP@InstanceName/Name/Version/ConfigFile/ClockEnableMode`, `Pin@Name/Position/Type/Variant`, `Signal@Name/IOModes` |
| `families.xml` | 1 | `Family@Name`(27) / `SubFamily@Name`(125), 2 711 `Mcu` entries in total (including variants; 2 016 devices after deduplication) |
| `db/mcu/IP/*_Modes.xml` | 1 321 | `IP@Name/IPType/Version/DBVersion` → `Mode/RefMode(Abstract,BaseMode)/Parameter/RefParameter/Signal/RefSignal(IOMode,ShareableGroupName,Virtual)/ModeLogicOperator/SignalLogicalOp/ConfigForMode/Semaphore/PossibleValue/Condition/Description/About` |
| `db/mcu/config/*_Configs.xml` | 1 308 | `RefConfig/CallLibMethod(ReturnHAL)/LibMethod/MethodArg(ParameterName)/Argument(AddressOf,GenericType,TypeName,Context,OptimizationCondition)/IFCondition(Expression)/ImplementCallBack/File(Category,Name)/RefComponent(Cclass,Cgroup,Cversion)/HardCode(Text)` |
| `db/mcu/memory` | 47 | Root `rzone` (memory regions for the H7RS/U5 series) |
| `db/mcu/packs/*.vpdsc` | 19 | CMSIS-Pack descriptions (`package`) |
| `db/contextual` | 364 | `ctx_periph_help / ctx_core_help / ctx_pinout_help` (GUI contextual help) |
| `db/plugins/boardmanager` | 215 pdsc + 430 ioc | Boards (`bsp/`, `boards/`) |
| `db/plugins/clock` | 64 | `Clock` tree definitions |
| `db/plugins/power` | 225 xml + json | `Battery/Consumption`, `rf/ble.json`, `subghz/tx_subghz.json` |
| `db/plugins/updater` | 4 | `STMUpdaterDefinitions.xml` (`SiteAccess Url=https://sw-center.st.com SiteRoot=/packs/resource/`, `SoftUpdates SiteSubPath=library/`, each `PackDescription Release/ReleaseSize/ReleaseMD5/Status` + `OS Type=win|mac|lin` + `DataBaseRelease ReleaseMax=DB.6.0.150`), `updaterThirdParties.xml` (direct links to third-party `.pack` files + `PackDependencies`), `PacksControlFlags.xml` (**Denied list**, e.g. Keil DFP), `cubemx.pidx` |
| `db/plugins/projectmanager` | 2 | `project.xml`, the misspelled `Toulchains.xml` |
| `db/plugins/mcufinder` | — | React front end `reactClient/`, `reactClient1/`, `images/packages/*_top.png` |
| `db/templates` | 1 756 ftl | See §5 |

### 6.1 Condition Expression Language (`analysis/condition_language.json`)

* **636 975** `Condition@Expression` entries (2 629 files, 0 parse failures).
* Lexicon: `&`, `|`, `!`, `=`, `>`, `<`, parentheses; identifiers = parameter names/mode names/signal names.
* Special references: `$IpNumber`, `$IpInstance`, `$IpInstanceCH0…CH12`, `$context`,
  `Semaphore_<name>$IpInstance` (e.g. `Semaphore_output_Channel$IpInstance`),
  die variables (`DIE483`, `DIE413`), `true`; functions `MOD(...)`, `IF(...)`.
* Security-related prefixes appear heavily on H5/H7RS: `S_SECURE`, `GTZC_S`, `FLASH_BB_PRIV/SEC`,
  `OB_BOOT_LOCK_ENABLE`, `OB_RDP_LEVEL_0`, `OB_DUALBANK_DUAL`.
* The actual set of `RefParameter@Type` values (including hand-written misspellings, recorded as a factual list):
  `list(132 600) / string(52 947) / integer(36 605) / double / hex / boolean / String /
  stringRW(5 536) / integerReadOnly(1 458) / uniqueElementList(1 824) /
  UniqueElementList(1 725) / Array / List / StringRW / StringW / RWString / RWstring /
  decimal / subtitle / polynomial / polynomialOdd / polynomialodd / StringHex /
  doubleReadOnly / doubeReadOnly / IntregerReadOnly / interger / intger / u8niqueElementList / Integer / Hex / Int / bool / int …`
* `PossibleValue@Action`: `Disable(51 083) / DISABLE(2 036) / Remove(3 705) /
  ENABLE(1 251) / remove(1 165) / disable(339)`, plus a legacy usage that puts peripheral names into Action
  (`XSPI1/XSPI2/SDMMC1/SDMMC2`).
* `Group`/`Unit` vocabulary: `REGISTERS`, `BB Pages`, `NOR/PSRAM timing`,
  `Advanced Parameters`…; units `MHz/KHz/Hz/ns/Bytes/Bits/s/V/Byte(s)`.
* IPs with the most conditions: `UART/TIM/ETH/flash/RCC/SMARTCARD/USART/SPI/FDCAN/RTC`.

> The MCP's `ip_param_get/ip_param_set` only change values; **validity checking is left to the engine**
> (the `value_check` tool calls `possible_value`/`not_a_possible_value` directly),
> because these expressions also depend on die/semaphore/context runtime state.

### 6.2 `.ioc` Syntax (`analysis/ioc_grammar.json`)

Statistics over 506 real `.ioc` files (215×2 boards + user projects + generated samples) yield **7 670 key patterns**:

* Fixed header: `File.Version=6`, `Mcu.Family/Name/Package/PinsNb/IPNb`,
  `KeepUserPlacement=false`, `CAD.formats/CAD.pinconfig/CAD.provider`,
  `MxCube.Version`, `MxDb.Version`, `PB.ProgrammerPrivileges`, etc.
* Indexed lists: `Mcu.Pin0…Mcu.PinN` (30 896 occurrences), `Mcu.IP0…` (4 704 occurrences),
  with `Mcu.PinsNb`/`Mcu.IPNb` as the counts; values are **full pin names** (`PC13-TAMPER-RTC`,
  `PD0-OSC_IN`, `VP_<IP>_<Signal>`).
* Pin attributes (by pattern occurrence): `PIN.Signal`(30 289) `PIN.Locked`(27 887)
  `PIN.GPIOParameters`(25 354) `PIN.GPIO_Label`(23 013) `PIN.Mode`(10 534)
  `PIN.PinAttribute`(5 908) `PIN.GPIO_PuPd/GPIO_Speed/GPIO_Mode`.
* IP attributes: the `<IP>.IPParameters` registration list determines whether the remaining keys are persisted;
  `RCC.`(28 555) is the largest namespace, followed by `RIF.`(20 668), `SH.`(16 937, FMC/OSPI pin multiplexing),
  `NVIC.`(3 924), `PCC.`(1 977).
* Escaping: `:` within values is written as `\:`; `NVIC.<IRQ>` keys themselves carry `:` semantics (e.g.
  `NVIC.USART1_IRQn,0,true:ENABLE,1,`).
* The full set of `ProjectManager.*` keys (toolchain, `FirmwarePackage`, `CustomerFirmwarePackage`,
  `functionlistsort`, heap/stack, `BackupFolder`, `KeepUserCode`, `UAScriptBefore/After` …)
  is covered by the read/write implementation in `mxmcp/ioc.py` and the `project_options` tool.

---

## 7. Persistent Runtime State

| Location | Contents |
|---|---|
| `~/.stm32cubemx/` | `log4j2.xml` (console+file), `STM32CubeMX.log`, `cad_preferences.json`, `mxinstallversion.txt`, `favorites.mcus.txt` / `favorites.boards.txt`, `ThirdParty.prefs`, `db.json`, `.jxbrowser-8.5.0/Chromium/` (Chromium 134.0.6998.89 unpacked on first run, including `.sig` and `extraction.lock`) |
| `~/.stmcufinder/plugins/mcu/` | `cube-finder-db.db` (86 MB SQLite, **19 tables**), `cube-finder-db.zip`(43 MB), `api_config.json`, `mcuFinder.mfd`, `md5.xml`, `tutoVideoDB.json/.zip`, `mcusAds.json`, `additional_hw_images/*.jpg` |
| `~/STM32Cube/Repository/` | Firmware package directories `STM32Cube_FW_<FAM>_V<x.y.z>` (completeness criterion: `package.xml` + `Drivers/`); on this machine only `FW_F1_V1.8.0` is complete (`Release="FW.F1.1.8.0" Patch="FW.F1.1.8.6"`) |
| Registry | `HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\STM32CubeMX` (IzPack), `...\App Paths\STM32CubeProgrammer.exe` (including Wow6432Node) used to locate `STM32_Programmer_CLI` |
| Project directory | `.ioc`, `project_ext.ioc` (`*.Ext` completed values), `.mxproject`, `mxcube_log.txt` |

**Selection database structure** (`analysis/mcufinder_data_layer.json`, read-only SQLite):
`attribute(232)`, `cpn(17 491)`, `cpn_has_attribute(644 828)`, `cpn_relates_to_cpn`,
`feature(1 807)`, `featureitem(5 482)`, `prmis_class(30)`,
`prmis_class_has_attribute(514)`, `resource(2 766)`, `rpn(14 550)`,
`rpn_has_attribute(143 130)` … — a typical EAV: commercial part number (CPN)/order code (RPN)/attributes/resources/features.
The MCP queries it directly through the `product_db` tool (read mode, no writes).

**React↔Java bridge** (`analysis/jxbrowser_bridge.json`): the front end exposes only 3
`window.java.*` callbacks (`getCustomPinsAsString`, `getOnlyCustomPinsAsString`,
`getStandardPinsAsString`), i.e. the "export pin assignment from the selection page" path; all other data goes through the local
`cube-finder-db.db` and the `ApiDb/DbMcus/DbBoards/DbExamplesSqlite` Java layer;
the only external endpoints are `api.ultralibrarian.com/api/v1` (price comparison) and `cdn.jsdelivr.net` (styles).

---

## 8. Network and Authorization Surface

| Endpoint | Purpose |
|---|---|
| `https://sw-center.st.com/packs/resource/`, `library/` subpath | Firmware/DB/MX self-updates (`STMUpdaterDefinitions.xml`); downloads are verified using `md5.xml` |
| `https://sw-center.st.com/packs/cube-finder-db/md5.xml`, `/packs/cubeanalytics/` | Selection database and analytics package |
| `https://my.st.com/cas/login` (with `?service=`) | CAS login |
| `https://stm32cube-ua.st.com/api/user_service/login/callback?code=` | OAuth callback (userauth) |
| `https://mcucrossselector.codex.cro.st.com`, `xsel.stmcufinder.com`, `https://artifacts.st.com:443/artifactory/mcd-cubemx-maven-local/` | Cross-selection / artifacts |
| `https://api.ultralibrarian.com/api/v1` | Pricing and alternative parts |
| `https://eds.st.com`, `https://wiki.st.com/stm32mcu/…`, `https://www.st.com/bin/st/getAd.json` | Help and ads |
| `https://www.google-analytics.com/collect` | Telemetry (controlled by `user_analytics` and the privacy notice) |
| `HKLM App Paths\STM32CubeProgrammer.exe` | Locating the local CubeProgrammer (secure boot programming) |

`swmgr connection status` uses an HTTP probe; `proxy type` supports
`NO_PROXY/SYSTEM_PROXY/USER_PROXY`; `swmgr hello` checks the proxy state first (keep this in mind for offline environments).

---

## 9. Test/Internal Tool Surface (also retained)

`xts` (compliance test suite), `xtest`, `xbuild`, `xcopy` (9 arguments),
`ocxtest`, `tooltip log on/off` (writes GUI tooltip text to the log), `popupwrapper`
(`record_answer/clear/set`, for unattended popups), `updateIpUI <ip>`,
`isPluginError <plugin>`, `simulate cubeIDE <bool>`, `user_analytics <bool>`,
`import hackmxdb` (database hot-patch mode), `check mcus xml/modes` (whole-database health check),
`get codegeneratormode`, `bootpath wizard`.
In the MCP these are covered by `compliance`, `ide_bridge`, `porting` and `cli` respectively.

---

## 9.5 RTOS / Middleware (settled by testing)

This area was only settled through runtime forensics, and is a classic case of "looks like it works but actually loses data":

| Fact | Evidence |
|---|---|
| "Enabling" a middleware IP is not `Mcu.*.Mode`; instead its name is written into `Mcu.IP0..N` (`Mcu.IP3=FREERTOS`) | Comparison of board `.ioc` files against runtime `config saveext` |
| `set mode FREERTOS CMSIS_V2` **does take effect** (log `Current active RTOS is FREERTOS [Cortex-M3NS]`), but the entire RTOS table appears only in the **extended save** `project_ext.ioc` (`FREERTOS.Tasks01=…`, `FREERTOS.config*.Ext=…`, `FREERTOS.Mutexes01.Ext=` and 60+ other keys) | `build/mw2/project_ext.ioc` |
| `project.ioc` (a normal `config saveas`) **does not contain** these defaults, so reading only the main file wrongly concludes "RTOS is not enabled" | Same as above, plus the `FREERTOS.*` statistics in `analysis/ioc_grammar.json` |
| Object format: `<PREFIX>.<list name><two-digit index>=field1,field2,…`, with field order declared by `rtos_apis.xml`; keys are only persisted if listed in `IPParameters` | `FREERTOS.Tasks01=defaultTask,24,128,StartDefaultTask,Default,NULL,Dynamic,NULL,NULL` |
| CMSIS v1 has 7 object types / v2 has 8 (tasks, queues, timers, binarySems, countingSems, mutexes, recursiveMutexes, events), with 35/40 fields | `analysis/rtos_model.json` |
| Field availability is decided by **JavaScript** (`allocationType === 'Static'`), evaluated by GraalJS + `RtosBindings` | `<enabled condition>` in `docs/rtos_apis.xml` |
| Custom middleware is registered with `add mw <name> <root_dir> <mode_file> <config_file> <template_dir>` (5 arguments) | Usage string echoed by bare `add` |
| Order of effect: modify `.ioc` → `config load` → `config saveext`; CubeMX recomputes the derived tables itself | Implementation and tests of `rtos_object_write` |

Corresponding tools: `rtos_schema` / `rtos_status` / `rtos_objects` / `rtos_object_write` /
`rtos_config` (after writing, forces an engine reload+save so that the .ioc stays authoritative).

## 10. Remaining Uncertainties (honestly flagged)

1. `MMT *` returns KO and echoes the global usage on MCUs without the memory mapping feature (F1); the full region semantics on H7RS/U5/N6
   can only be observed with the corresponding firmware packages and projects (the full packages are not installed in the local repository).
2. `get sub-modes <IP>` glues the body text and the terminator onto the same line, and the body is repeated twice
   (`No DebugSysTickNo DebugSysTick0 OK`); the engine already frames by "trailing terminator", but
   the trailing digits may be mixed into the body, so the return value of `submode_state` should be treated as text.
3. The full module graph of the React client was not built (the single file `main.d8df2386.js` made REA's JS worker
   exceed a 1 024 MiB heap; a literal scan was used to obtain the bridge interface and the set of endpoints).
4. `third_parties_plugins/com.st.stm32cube.ide.common.services.mx.jar-1.19.0-b1.jar`
   (62 MB, only 30 entries: it is itself a nested bundle aggregating the services) was not expanded class by class.
5. `import hackmxdb` and `bootpath wizard` modify the DB or open a wizard, so only their usage was recorded; they were not actually run.
