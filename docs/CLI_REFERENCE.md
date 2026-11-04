# STM32CubeMX CLI Reference (tested + decompiled, v6.15.0)

This file is the behavioral basis for `mxmcp`: every entry has been run successfully or confirmed by decompilation on a local CubeMX 6.15.0.
The `cli` / `cli_batch` tools can execute any of the commands below; all other tools are typed wrappers around these commands.

Launch methods (official, also documented in UM1718):

```bat
rem Interactive
jre\bin\java -jar STM32CubeMX.exe -i
rem Script + no UI (the MCP session engine uses this one for cold starts/batch processing)
jre\bin\java -jar STM32CubeMX.exe -q script.txt
rem Script + UI
jre\bin\java -jar STM32CubeMX.exe -s script.txt
```

## 1. Interaction Protocol (`-i`)

* The prompt `MX> ` has **no trailing newline**; the command is echoed, then the result is output, and the last line is `<n> OK` or `<n> KO`.
* `n` is an internal engine counter; do not rely on its specific value.
* After operations that print nothing (`set pin`, `set mode`, `config saveas`), the prompt sits alone on its own line;
  the response to the next command may be appended to the same physical line (`MX> PC13: GPIO_Output`), so the `MX>` prefix must be stripped.
* Some list-type responses are printed twice by the engine itself (`USART1: Asynchronous, USART1: Asynchronous,`,
  `GPIO_OutputPC13-TAMPER-RTC: GPIO_Output`); the parser deduplicates them.
* **Important**: if a command cannot return because of a popup dialog/download, the interpreter locks up and all subsequent commands time out.
  The `mxmcp` session engine kills the process on timeout and recovers by re-running `config load` on the next call.

## 2. Command Summary (89 registered entries, from the `addCommand` constant pool in plugins/**)

| Family | Subcommands and semantics |
|---|---|
| `load <mcu>` | Create a new project. **Accepts only the db RefName** (`STM32F103C(8-B)Tx`); passing a bare part number `STM32F103C8T6` makes the interpreter hang forever. |
| `tinyload <mcu>` | Load only the pinout, without creating a project. |
| `loadboard <board> <allmodes\|nomode>` | Board project; `nomode` includes only the default pins, `allmodes` includes all peripheral default modes. |
| `config load/save/saveas/saveext <file>` | Read/write .ioc. `save` hangs on an uninitialized path; the MCP uses only `saveas`/`saveext`. |
| `import config <file>` / `import openioc` | Merge another .ioc into the current project. |
| `get pinout` | Full `pin: signal` table. |
| `get functions <pin>` | Signal names available for this pin. The full name `PC13-TAMPER-RTC` can be passed. |
| `get signal <pin>[/regex]` | Current signal of a single pin. |
| `set pin <pin> <signal>` | Assign a signal; both the short name `PC13` and the full name are accepted. |
| `reset pin <pin>` / `reset pin-signal` / `reset signal <signal>` | Unassign. |
| `clearpinout` | Clear all pins. |
| `lock pin <pin> <true\|false>` | Lock/unlock a pin. |
| `set pinreservation <pin>` | Reserve a pin. |
| `get modes/available modes/all/mapped modes <regex>` | Peripheral modes (all/available/set). |
| `get mode active/available/all <periph>` | Mode details for a single peripheral. |
| `set mode <periph> "<mode>"` | Enable a mode; **the mode name must be quoted**. |
| `reset mode <periph> "<mode>"` | Disable a mode. |
| `check mode enabled <periph> "<mode>"` | Whether it is enabled. |
| `check mcu modes` | List of modes unavailable on the current MCU. |
| `check mcus xml` / `check mcus modes` | Self-check of the entire database (very slow). |
| `get sub-modes <periph>` / `get sub-mode-state <periph> <path>` | Composite mode state. |
| `get mcu name/package/peripherals` | MCU information. |
| `get ip parameters <ip> <param>` | Read a parameter. |
| `set ip parameters <ip> <param> <value>` | Write a parameter. |
| `set ip parameters <ip> IPParameters a,b,c` | **Register parameter names in the `.ioc` `IPParameters`**; unregistered parameters are kept only in memory and not persisted. |
| `set username <ip> <name>` | Rename the instance (affects the generated code prefix). |
| `get gpio parameters <pin> <param>` / `set gpio parameters <pin> <param> <value>` | GPIO parameters; **pin must be the full name** (`PC13-TAMPER-RTC`). |
| `get available-analog-signals <pin>` | Analog channels. |
| `get possible remaps <signal regex>` | Remap pins. |
| `NVIC enable/disable/set_priority/set_subpriority/set_prioritygroup ...` | Interrupt configuration (confirmed from `export script` recordings). |
| `clock resolution` | Clock tree solving/convergence. |
| `project path/name/toolchain/compiler/toolchainlocation <v>` | Project target settings. `project compiler` only applies to multi-compiler toolchains. |
| `project couplefilesbyip <0\|1>` | Separate files per IP / everything in main. |
| `project generateunderroot <0\|1>` | Generate into the project root directory. |
| `project setCustomFWPath "<dir>"` | Specify the firmware package directory; when written to the .ioc it is **converted to a path relative to the .ioc**. Setting it alone is not enough to bypass the online check; the `ProjectManager.FirmwarePackage` version must also match the repository directory. |
| `project set/get stacksize, heapsize` | Stack/heap size. |
| `project set/get stackbycontext, heapbycontext <ctx>` | Per-context for multi-core. |
| `project save` / `project import` | Save/load project settings. |
| `project generate` | Generate the full project (code + drivers + IDE project). If the firmware package is missing it waits for network access/login → hangs without UI. |
| `generate code <dir>` | Generate only the MX code. |
| `generate all_code_in_main` / `generate one_file_per_ip` | Generation layout. |
| `SetStructure Advanced\|Basic` | Project structure. |
| `SetCopyLibrary "copy all"\|"copy only"\|"copy as reference"` | Library copy mode. |
| `setDriver <periph> HAL\|LL` | Driver layer selection. |
| `csv pinout <file>` | Pin CSV export (`purpose,position,name,type,signal,label,...`). |
| `export script <file>` | **Export the current configuration as a replayable command script**. |
| `loadboard`, `add mw <name> <root> <mode> <config> <templates>` | Custom middleware (.mw project). |
| `pack enable/disable/validate/context/migrate/status` | CMSIS-Pack components. |
| `swmgr refresh/install/remove/set repository/set proxy ...` | Cube firmware packages and package management. |
| `login <email> <password> <y\|n>` / `logout` / `login_with_gui` | ST account. |
| `xcopy`, `xts`, `xtest`, `xbuild`, `ocxtest`, `xcubedl <pack>` | Example project copy/test/build/download. |
| `MultiConfig selectMXProject/selectLPBAMConfiguration/addLPBAMConfiguration/renameLPBAMConfiguration/deleteLPBAMConfiguration/getLPBAMConfigurations` | Multi-configuration and LPBAM. |
| `pinout check/uncheck keep user placement` | Keep user placement. |
| `updateIpUI <IpName>`, `tooltip log on/off`, `isPluginError <plugin>`, `log <level>` | Diagnostics. |
| `simulate cubeIDE <true\|false>`, `user_analytics <true\|false>` | Environment switches. |
| `setprop/getprop/getenv` | JVM properties/environment variables. |
| `popupwrapper set/unset/record_answer/unrecord_answer` | Popup answer injection (scripting GUI dialogs). |
| `cpload project1|project2`, `cpexport` | Configuration comparison (copy/paste projects). |
| `import try import`, `import try import_and_log`, `import try auto`, `import get report` | Cross-MCU import report. |
| `import hackmxdb`, `import GPIOconstraint`, `import channelconstraint`, `import add_compatibility_rule` | Pin/channel constraints and compatibility rules. |
| `possible_value ip` / `not_a_possible_value ip` | Parameter value validation. |
| `disable project generate <true\|false>` | Disable the Generate button. |
| `exit` / `exit_mx` | Exit. |

## 3. `.ioc` Format Essentials

```
#MicroXplorer Configuration settings - do not modify
Mcu.Name=STM32F103C(8-B)Tx        <- db RefName
Mcu.UserName=STM32F103C8Tx        <- part number entered by the user
Mcu.Pin0=PC13-TAMPER-RTC          <- full pin name (not PC13)
Mcu.IP0=USART1
PA9.Signal=USART1_TX
PA9.Mode=Asynchronous
PA9.Locked=true
PC13-TAMPER-RTC.GPIOParameters=GPIO_Label
PC13-TAMPER-RTC.GPIO_Label=LED
USART1.IPParameters=VirtualMode   <- only parameters listed here are saved
RCC.IPParameters=...
RCC.PLLMUL=RCC_PLL_MUL9
RCC.PLLSourceVirtual=RCC_PLLSOURCE_HSE
RCC.HCLKFreq_Value=72000000       <- solved result, read-only
ProjectManager.TargetToolchain=Makefile
ProjectManager.FirmwarePackage=STM32Cube FW_F1 V1.8.0
ProjectManager.CustomerFirmwarePackage=..\..\..\STM32Cube\Repository\STM32Cube_FW_F1_V1.8.0
```

Notes:
* Colons in values are written as `\:` (e.g. `NVIC.SysTick_IRQn=true\:15\:0\:...`).
* For the HSE clock tree to take effect, `PD0-OSC_IN.Signal=RCC_OSC_IN` and `PD1-OSC_OUT.Signal=RCC_OSC_OUT` are required;
  setting only `PLLSourceVirtual=RCC_PLLSOURCE_HSE` without multiplexing the pins still solves the clock tree from HSI (8 MHz).
* Pinning the firmware version: `ProjectManager.FirmwarePackage` must match the version of the actually installed directory,
  otherwise `project generate` will try to download online. Change the version to the actual version of the complete package in the repository and combine it with `project setCustomFWPath` to avoid network access entirely.

## 4. Verified Generation Behavior

| Scenario | Result |
|---|---|
| Configure within a CLI session → `project generate` (F1, firmware package version matches) | OK, about 5 s, 913 files, including `Src/main.c`, `Drivers/`, `Makefile` |
| Load .ioc → `project generate`, firmware version mismatch | One KO + `This download action requires prior login` (no hang) or a hang (online access without UI) |
| After the first generation fails (login prompt), set `project setCustomFWPath <absolute path>` + align the `FirmwarePackage` version → reload and generate again | OK, 234+ files, no login required |
| Toolchains EWARM / MDK-ARM / STM32CubeIDE / Makefile / CMake | All generate successfully; 700–1300 files when the firmware package is present |

