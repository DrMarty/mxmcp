# 独立模式：不依赖 CubeMX 安装

mxmcp 有两种运行模式，同一个 MCP 接口、同一套工具名（`standalone_*` 除外）：

| 模式 | 何时 | 数据来源 | 能做什么 |
|---|---|---|---|
| **hybrid**（默认，装了 CubeMX） | `MXMCP_CUBEMX_ROOT` 指向真实安装 | 安装目录 + 官方引擎 | 全部工具，包括 `project_generate` 的 ST 原版代码 |
| **standalone**（无安装） | 安装目录不存在 / 未设置 | 自带数据包 `mxmcp/data/cubemx-db.zip` | 选型、引脚、模式、参数、NVIC、校验、`.ioc`、C 代码生成 |

服务器启动时自动判断，`standalone_info` 会报告当前模式。

---

## 1. 数据包

```
mxmcp/data/cubemx-db.zip   9.1 MB（gzip 成员）
├── mcu/<Family>/<RefName>.json   2 019 颗 MCU
│     引脚（name/type/position + 可复用信号 + GPIO IOModes）
│     IP 实例（name/instance/version）、core/flash/ram、封装
├── families.json                 27 家族 / 125 子家族
├── boards.json                   215 块官方板卡
├── ip_modes.json                 274 个 IP 的模式 + 参数 schema（含 IP 类型）
├── config_slim.json              192 个 IP 的 HAL Init 参数树 + 调用序列（生成器用）
├── templates.json                1 756 个 .ftl 的清单与 sha256
├── middleware.json               36 个中间件实例名 + 常量映射
├── rtos_model.json               CMSIS RTOS1/2 的对象模型（15 类 / 75 字段）
├── cli_registry.json             267 条 CLI 注册（供 command_catalog）
└── meta.json                     构建来源与计数
```

**构建**（只需在装了 CubeMX 的机器上做一次）：

```bat
python -m mxmcp.bundle build --cubemx-root "C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX"
python -m mxmcp.bundle info      :: 查看内容与计数
python -m mxmcp.bundle verify    :: 逐成员完整性校验
```

`MXMCP_DATA_PACK` 可指向别处的包；默认用 `mxmcp/data/cubemx-db.zip`。
包里**没有**任何 ST 的二进制或源码，只有从公开安装件里抽取的数据投影。

## 2. 独立引擎（`mxmcp/standalone.py`）

在内存里维护与 `.ioc` 同构的工程模型，并做**真实校验**：

* 引脚只能绑定该引脚在 MCU xml 里声明的信号（`PA9` 只有 `TIM1_CH2/USART1_TX/GPIO…`）
* `GPIO` 的 `IOModes` 展开为 CLI 用的 `GPIO_Input/Output/ANALOG/EVENTOUT/EXTI0..15`
* 同一信号只能绑一次；重复绑定会把旧引脚释放
* IP 必须是该 MCU 上真实存在的实例
* 模式必须是 `db/mcu/IP/*_Modes.xml` 声明的模式
* `IPParameters` 自动登记，参数才持久化（与官方同规则）

```text
standalone_create   {mcu: "STM32F103C8T6", name: "blink"}
  -> STM32F103C(8-B)Tx, LQFP48, 44 pins
standalone_signals  {project_id: "blink", pin: "PA9"}
  -> TIM1_CH2, USART1_TX, GPIO_Input, GPIO_Output, GPIO_ANALOG, GPIO_EVENTOUT, GPIO_EXTI0…
standalone_pin      {project_id: "blink", pin: "PA9", signal: "USART1_TX"}
standalone_pin      {project_id: "blink", pin: "PA9", signal: "USART3_TX"}   # 被拒绝并给出建议
standalone_mode     {project_id: "blink", ip: "USART1", mode: "Asynchronous"}
standalone_param    {project_id: "blink", ip: "USART1", param: "BaudRate", value: "115200"}
standalone_nvic     {project_id: "blink", irq: "USART1_IRQn", priority: 1, enabled: true}
standalone_validate {project_id: "blink"}      -> ok: true
standalone_generate {project_id: "blink", output_dir: "out/blink"}
```

## 3. 独立代码生成（`mxmcp/codegen.py`）

生成链：`.ioc` 参数 → `config_slim.json` 里的 `HAL_<IP>_Init` 参数树 →
逐个字段赋值 → 文件骨架。

产物（Makefile 工具链为例）：

```
out/blink/
├── Core/Inc/main.h
├── Core/Src/main.c                 main() + SystemClock_Config + MX_<IP>_Init + MX_GPIO_Init
├── Core/Src/stm32f1xx_hal_msp.c    HAL_<IP>_MspInit 回调
├── Core/Src/stm32f1xx_it.c         已启用中断的处理函数
├── Core/Src/system_stm32f1xx.c     SystemCoreClock 桩
└── Makefile                        arm-none-eabi，自动挂载 Drivers/
```

参数赋值是**真实推导**的：

```c
static void MX_USART1_Init(void)
{
  husart1.Init.BaudRate = 115200;  /* from .ioc */
  husart1.Init.Mode = Asynchronous;  /* from .ioc */
}
```

限制（明确写进返回值 `fidelity: "standalone"`）：不复刻 ST 的 1 756 个 FreeMarker
模板与产品级逻辑，因此时钟树初始化、外设句柄全局声明、中断优先级寄存器设置
需要用户补齐或配合 `Drivers/`（CMSIS+HAL，来自固件包）。要 ST 原版输出，
用装好的 CubeMX 跑 `project_generate`。

## 4. 无安装时引擎工具的行为

所有需要 JVM 的工具在调用时**立刻**返回可操作错误，而不是等超时：

```
CubeMX is not installed at <root>, so the engine-backed tools cannot run.
Use the standalone tools instead (no installation needed):
  standalone_info / standalone_create / standalone_pin /
  standalone_mode / standalone_param / standalone_nvic /
  standalone_validate / standalone_generate
To enable the full engine, install STM32CubeMX and point
  MXMCP_CUBEMX_ROOT  at the installation directory.
```

## 5. 验收

```bat
python tests\test_standalone.py     :: 把 MXMCP_CUBEMX_ROOT 指到不存在的目录
```

实测输出（Windows，无 CubeMX 路径）：

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
main.c 含 BaudRate = 115200: True
engine tool without install -> clean error: True
```

## 6. 只靠自带数据也能用的工具

`standalone_*`（10 个）+ `mcu_search` `mcu_info` `family_list` `family_mcus`
`mcu_pin_functions` `board_list` `board_search` `catalog_index` `ip_library`
`template_list` `mode_catalog` `middleware_list` `rtos_schema` `command_catalog`
`product_db` `ioc_get` `ioc_set` `ioc_delete` `ioc_import` `ioc_export`
`project_diff` `firmware_packages`（扫描本地仓库）`standalone_validate/view`。

按族见 [FEATURES.md](FEATURES.md) 的"离线"列。
