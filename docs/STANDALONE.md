# Standalone mode: no CubeMX installation required

mxmcp has two run modes, with the same MCP interface and the same set of tool names (except `standalone_*`):

| Mode | When | Data source | What it can do |
|---|---|---|---|
| **hybrid** (default, CubeMX installed) | `MXMCP_CUBEMX_ROOT` points to a real installation | Installation directory + official engine | All tools, including ST's original code from `project_generate` |
| **standalone** (no installation) | Installation directory missing / not set | Bundled data pack `mxmcp/data/cubemx-db.zip` | MCU selection, pins, modes, parameters, NVIC, validation, `.ioc`, C code generation |

The server detects the mode automatically at startup; `standalone_info` reports the current mode.

---

## 1. Data pack

```
mxmcp/data/cubemx-db.zip   9.1 MB (gzip members)
├── mcu/<Family>/<RefName>.json   2 019 MCUs
│     pins (name/type/position + remappable signals + GPIO IOModes)
│     IP instances (name/instance/version), core/flash/ram, package
├── families.json                 27 families / 125 subfamilies
├── boards.json                   215 official boards
├── ip_modes.json                 modes + parameter schema for 274 IPs (including IP type)
├── config_slim.json              HAL Init parameter trees + call sequences for 192 IPs (used by the generator)
├── templates.json                list and sha256 of 1 756 .ftl files
├── middleware.json               36 middleware instance names + constant mappings
├── rtos_model.json               CMSIS RTOS1/2 object model (15 classes / 75 fields)
├── cli_registry.json             267 CLI registrations (for command_catalog)
└── meta.json                     build provenance and counts
```

**Build** (only needs to be done once, on a machine with CubeMX installed):

```bat
python -m mxmcp.bundle build --cubemx-root "C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX"
python -m mxmcp.bundle info      :: show contents and counts
python -m mxmcp.bundle verify    :: per-member integrity check
```

`MXMCP_DATA_PACK` can point to a pack elsewhere; the default is `mxmcp/data/cubemx-db.zip`.
The pack contains **no** ST binaries or source code, only data projections extracted from the publicly available installation.

## 2. Standalone engine (`mxmcp/standalone.py`)

Maintains an in-memory project model isomorphic to `.ioc`, and performs **real validation**:

* A pin can only be bound to signals declared for that pin in the MCU xml (`PA9` only has `TIM1_CH2/USART1_TX/GPIO…`)
* `GPIO` `IOModes` are expanded to the CLI's `GPIO_Input/Output/ANALOG/EVENTOUT/EXTI0..15`
* A signal can only be bound once; binding it again releases the previous pin
* The IP must be an instance that actually exists on that MCU
* The mode must be one declared in `db/mcu/IP/*_Modes.xml`
* `IPParameters` is registered automatically; only then are parameters persisted (same rule as the official tool)

```text
standalone_create   {mcu: "STM32F103C8T6", name: "blink"}
  -> STM32F103C(8-B)Tx, LQFP48, 44 pins
standalone_signals  {project_id: "blink", pin: "PA9"}
  -> TIM1_CH2, USART1_TX, GPIO_Input, GPIO_Output, GPIO_ANALOG, GPIO_EVENTOUT, GPIO_EXTI0…
standalone_pin      {project_id: "blink", pin: "PA9", signal: "USART1_TX"}
standalone_pin      {project_id: "blink", pin: "PA9", signal: "USART3_TX"}   # rejected, with suggestions
standalone_mode     {project_id: "blink", ip: "USART1", mode: "Asynchronous"}
standalone_param    {project_id: "blink", ip: "USART1", param: "BaudRate", value: "115200"}
standalone_nvic     {project_id: "blink", irq: "USART1_IRQn", priority: 1, enabled: true}
standalone_validate {project_id: "blink"}      -> ok: true
standalone_generate {project_id: "blink", output_dir: "out/blink"}
```

## 3. Standalone code generation (`mxmcp/codegen.py`)

Generation chain: `.ioc` parameters → `HAL_<IP>_Init` parameter tree in `config_slim.json` →
field-by-field assignment → file skeleton.

Output (Makefile toolchain as an example):

```
out/blink/
├── Core/Inc/main.h
├── Core/Src/main.c                 main() + SystemClock_Config + MX_<IP>_Init + MX_GPIO_Init
├── Core/Src/stm32f1xx_hal_msp.c    HAL_<IP>_MspInit callbacks
├── Core/Src/stm32f1xx_it.c         handlers for enabled interrupts
├── Core/Src/system_stm32f1xx.c     SystemCoreClock stub
└── Makefile                        arm-none-eabi, automatically mounts Drivers/
```

Parameter assignments are **actually derived**:

```c
static void MX_USART1_Init(void)
{
  husart1.Init.BaudRate = 115200;  /* from .ioc */
  husart1.Init.Mode = Asynchronous;  /* from .ioc */
}
```

Limitations (stated explicitly in the return value `fidelity: "standalone"`): it does not replicate ST's 1 756 FreeMarker
templates and product-level logic, so clock tree initialization, global peripheral handle declarations and interrupt priority register setup
must be completed by the user or supplied together with `Drivers/` (CMSIS+HAL, from the firmware package). For ST's original output,
run `project_generate` with an installed CubeMX.

## 4. Behavior of engine tools without an installation

Every tool that needs the JVM returns an actionable error **immediately** when called, instead of waiting for a timeout:

```
CubeMX is not installed at <root>, so the engine-backed tools cannot run.
Use the standalone tools instead (no installation needed):
  standalone_info / standalone_create / standalone_pin /
  standalone_mode / standalone_param / standalone_nvic /
  standalone_validate / standalone_generate
To enable the full engine, install STM32CubeMX and point
  MXMCP_CUBEMX_ROOT  at the installation directory.
```

## 5. Acceptance

```bat
python tests\test_standalone.py     :: points MXMCP_CUBEMX_ROOT at a nonexistent directory
```

Actual output (Windows, no CubeMX path):

```
tools: 113
mode: standalone | engine: False | pack: True 9107807
counts: {'mcu': 2019, 'pins': 245083, 'ips': 138565, 'families': 27, 'boards': 215, 'ip_modes': 274}
search: 1 ['STM32F103C(8-B)Tx']
create: STM32F103C(8-B)Tx LQFP48 pins: 44
PA9 signals: ['TIM1_CH2', 'USART1_TX', 'GPIO_Input', 'GPIO_Output', 'GPIO_ANALOG', 'GPIO_EVENTOUT']
pin: USART1_TX / USART1_RX / GPIO_Output
invalid pin signal rejected: True
mode/param/nvic: OK
validate ok: True []
generate: 6 files standalone
main.c contains BaudRate = 115200: True
engine tool without install -> clean error: True
```

## 6. Tools that work with only the bundled data

`standalone_*` (10 tools) + `mcu_search` `mcu_info` `family_list` `family_mcus`
`mcu_pin_functions` `board_list` `board_search` `catalog_index` `ip_library`
`template_list` `mode_catalog` `middleware_list` `rtos_schema` `command_catalog`
`product_db` `ioc_get` `ioc_set` `ioc_delete` `ioc_import` `ioc_export`
`project_diff` `firmware_packages` (scans the local repository) `standalone_validate/view`.

See the "Offline" column in [FEATURES.md](FEATURES.md) for the per-family breakdown.
