# mxmcp — STM32CubeMX 的 MCP 服务器（也可完全独立运行）

> 交付物：`mxmcp/`（服务器源码 + 自带数据包）、`tests/`（6 个测试脚本）、
> `docs/`（逆向记录、架构、数据模型、功能矩阵、独立模式、验收）、
> `analysis/`（机器可读逆向产物）、`tools/`（可复现的取证脚本）。

两种模式，同一个 MCP 接口：

* **hybrid**：装了 CubeMX 时驱动官方引擎（引脚/时钟/生成都是 ST 原版行为）。
* **standalone**：**不需要任何 CubeMX 安装** —— 自带 9.1 MB 数据包
  （2 019 颗 MCU / 245 083 引脚 / 274 套 IP 模式 / HAL Init 参数树），
  自带校验引擎与 C 代码生成器。见 [docs/STANDALONE.md](docs/STANDALONE.md)。

```
项目状态 (.ioc)  ←→  mxmcp (Python MCP server)  ←→  CubeMX CLI (常驻 JVM，可选)
                              ↑
                   自带数据包 cubemx-db.zip（离线选型/校验/生成）
```

## 1. 为什么这样做

* CubeMX 6.15.0 是 **PE32 装载器 + 内嵌 ZIP 的 Java 应用**（不是 native-image，
  **不需要脱壳**）：`java -jar STM32CubeMX.exe -q script.txt` 就是官方 headless 入口；
  内嵌归档 54 774 条目、起始 `0x13000`、中央目录 `0xD2F0A03`
  （`tools/rebuild_full_jar.py` 全量重建，0 失败）。
* 引擎内部有 **267 条** CLI 注册（旧记录只有 89 条，因为旧提取漏了
  `com/st/components`）、217 个插件 opcode；`export script` 能把任意工程序列化成
  可重放命令。
* 因此 MCP 不做“重新实现 CubeMX”，而是**受控前端**：写操作走官方解释器，
  读操作读 `.ioc`/自带数据包；两者可交叉校验（`verify` / `standalone_validate`）。

完整逆向记录：[ARCHITECTURE.md](docs/ARCHITECTURE.md)（总览）·
[REVERSE_ENGINEERING.md](docs/REVERSE_ENGINEERING.md)（过程）·
[DATA_MODEL.md](docs/DATA_MODEL.md)（数据结构）·
[CLI_REGISTRY.md](docs/CLI_REGISTRY.md)（267 条命令）·
[FEATURES.md](docs/FEATURES.md)（功能覆盖矩阵）·
[SECURITY_NETWORK.md](docs/SECURITY_NETWORK.md)（信任链与端点）·
[STANDALONE.md](docs/STANDALONE.md)（独立模式）

## 2. 运行要求

* Python 3.9+（**零第三方依赖**，只用标准库）
* STM32CubeMX **可选**：
  * 装了 → hybrid 模式，用官方引擎（默认路径
    `C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX`）
  * 没装 → standalone 模式，先建一次数据包
    `python -m mxmcp.bundle build --cubemx-root <安装目录>`（需要一台装了 CubeMX 的机器）
* 注意：仓库**不附带**数据包（ST 派生内容，见 [LICENSE](LICENSE)）。

环境变量（可选）：

| 变量 | 作用 | 默认 |
|---|---|---|
| `MXMCP_CUBEMX_ROOT` | CubeMX 安装目录 | `C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX` |
| `MXMCP_WORKSPACE` | 工程状态目录 | `~/.mxmcp` |
| `MXMCP_MAX_ENGINES` | 同时驻留的 JVM 数（每个打开工程一个） | `3` |

## 3. 接入 MCP 客户端

stdio 传输、JSON-RPC 2.0（换行分隔，也接受 `Content-Length` 帧）。

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

自检：

```bat
python -m mxmcp.server --list-tools
python -m mxmcp.server --selftest
python -m mxmcp.server --call catalog_index --args {}
```

## 4. 五分钟上手

```text
project_create {name: "blink", mcu: "STM32F103C8T6", toolchain: "Makefile"}
  -> project_id = blink
mcu_pin_functions {project_id: "blink", pin: "PA9"}      # 看可选信号
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

`project_generate` 返回文件清单与警告；典型结果：913 个文件、`Src/main.c`、`Drivers/`、
`Makefile`、`.ioc`，耗时约 5–10 秒（引擎已热）。

## 5. 工具一览（113 个）

**工程生命周期**：`project_create` `project_list` `project_get` `project_open`
`project_close` `project_save` `project_save_as` `project_delete` `project_diff`
`project_load_mcu` `project_load_board` `project_import_config` `project_export_script`
`project_options` `project_set_option` `project_report` `project_csv` `project_files`

**选型/资料（离线）**：`catalog_index` `mcu_search` `mcu_info` `mcu_pin_functions`
`family_list` `family_mcus` `board_search` `board_list` `ip_library` `template_list`
`firmware_packages` `mode_catalog` `command_catalog` `product_db` `middleware_list`

**引脚 / 外设**：`pinout_get` `pin_functions` `pin_set` `pin_reset` `pin_clear_all`
`pin_lock` `pin_reserve` `gpio_params` `gpio_set` `peripheral_list` `mode_list`
`mode_set` `mode_reset` `mode_check` `sub_modes` `submode_state` `mode_pattern`
`ip_param_get` `ip_param_set` `ip_params_set` `ip_params_dump` `ip_user_name`
`value_check`

**中断 / DMA / 内存映射**：`nvic_read` `nvic_write` `dma_query` `dma_mutate`
`mdma_query` `mdma_mutate` `gic_query` `gic_mutate` `mmt` `lpbam`

**RTOS / 中间件**：`rtos_schema` `rtos_status` `rtos_objects` `rtos_object_write`
`rtos_config` `middleware_add`

**时钟**：`clock_get` `clock_set` `clock_resolve` `clock_param_possible_values`

**生成 / 校验**：`project_generate` `generate_code` `verify` `compliance`

**移植 / 比较 / 选择器**：`porting` `ioc_compare` `selectors`

**软件包**：`pack_status` `pack_enable` `pack_disable` `pack_validate` `swmgr`
`xcubedl` `login` `logout`

**独立模式（无安装）**：`standalone_info` `standalone_create` `standalone_open`
`standalone_pin` `standalone_signals` `standalone_mode` `standalone_param`
`standalone_nvic` `standalone_view` `standalone_validate` `standalone_generate`
`standalone_mcu`

**`.ioc` 直写 / 兜底 / 运行时**：`ioc_get` `ioc_set` `ioc_delete` `ioc_import`
`ioc_export` `cli` `cli_batch` `cli_help` `runtime_props` `ide_bridge`

`cli` / `cli_batch` 能执行 [CLI_REGISTRY](docs/CLI_REGISTRY.md) 里的**任何**命令
（267 条），所以 MCP 接口是 CubeMX CLI 的超集：即使某个能力没有专门工具，也不会丢。
完整的功能→命令→工具对照见 [docs/FEATURES.md](docs/FEATURES.md)。

## 6. 关键行为与坑位（已在代码里处理）

1. **`load` 只认 db RefName**：`STM32F103C8T6` 会让解释器永久挂起；`project_create`
   会先用本地库把料号解析成 `STM32F103C(8-B)Tx`。
2. **参数不登记不落盘**：`ip_param_set`/`clock_set` 自动把参数名并入 `<IP>.IPParameters`。
3. **`config save` 在无路径时挂起**：只用 `saveas`/`saveext`，并在保存后回读校验。
4. **引擎卡死会污染后续调用**：会话引擎超时即杀进程，下次调用自动 `config load` 恢复；
   返回值里 `hung: true` 会明确告知。
5. **固件包版本必须匹配**：`.ioc` 里的 `FirmwarePackage` 与实际安装目录不一致时，
   `project generate` 会尝试联网（无 UI 下可能挂起）。生成前会预检；缺包时自动
   改用 `project setCustomFWPath` 指向已安装的同族包并重新固定版本，再生成。
6. **首次生成可能只拷贝驱动**：CubeMX 偶尔第一遍只做驱动拷贝；工具会检测
   “有 Drivers 无 main.c”并自动再生成一次。
7. **GPIO 参数要完整引脚名**：`PC13` → `PC13-TAMPER-RTC`，工具会自动解析。
8. **HSE 时钟树**：只设 `PLLSourceVirtual=HSE` 而不复用 OSC 引脚时时钟树仍按 HSI 求解；
   `clock_set` 会自动把 `OSC_IN/OSC_OUT` 复用成 `RCC_OSC_IN/OUT`，并在结果里给出 warning。
9. **派生时钟值要存两次**：CubeMX 在 *save* 时才计算 `PLLCLKFreq_Value` 等派生量。
   可靠节奏是 **写入 → save → reload → save**（实测 8 MHz → 72 MHz），已固化在
   `clock_set` 的多轮收敛里；手工用 `cli` 复现时务必照此顺序。
10. **没有 `.ioc` 时别依赖已启动的引擎**：引擎被回收再启动是空工程，
    `config saveas` 会抛 `Mcu.getDie()` NPE。先 `project_save` 一次再继续。
11. **中间件 IP 的 `set mode` 不带引号**：`set mode FREERTOS CMSIS_V2`；`get modes`
    对中间件返回 KO，`mode_list` 会自动回退到 `db/mcu/IP/*_Modes.xml`。
12. **RTOS 对象只在扩展保存里**：`project_ext.ioc` 才有 `FREERTOS.Tasks01` 等；
    读状态要合并视图，写完必须让引擎重新加载一次。

## 7. 目录

```
mxmcp/
├── mxmcp/                    服务器源码（零第三方依赖）
│   ├── server.py             MCP 入口（stdio；--selftest/--list-tools/--call）
│   ├── rpc.py                JSON-RPC 2.0 / MCP 协议
│   ├── engine.py             CubeMX 会话引擎（-i 常驻 + 三种成帧）
│   ├── store.py              工程池、保存/加载、料号解析
│   ├── ioc.py                .ioc 读写（含 project_ext.ioc 合并视图）
│   ├── catalog.py            安装目录索引（无安装时自动走数据包）
│   ├── bundle.py             数据包 build/info/verify + Pack 读取
│   ├── standalone.py         独立引擎（引脚/模式/参数/NVIC，真实校验）
│   ├── ipmodes.py            IP 模式与参数 schema
│   ├── codegen.py            独立 C 代码生成
│   ├── firmware.py           固件包完整性扫描
│   └── tools_*.py            113 个 MCP 工具
├── tests/                    6 个测试脚本
│   ├── test_units.py         解析/参数/固件预检（含真实生成）
│   ├── test_e2e.py           MCP 全流程（F1/F4/板卡）
│   ├── test_advanced.py      dma/nvic/gic/mmt/porting/selectors/catalog
│   ├── test_rtos.py          RTOS 对象读写与校验
│   ├── test_middleware.py    中间件集成
│   └── test_standalone.py    把安装路径指到不存在，验证独立模式
├── tools/                    取证与构建脚本（不是运行时依赖）
├── docs/                     逆向与使用文档
├── analysis/                 机器可读逆向产物（本地生成，不发布）
├── LICENSE  CONTRIBUTING.md  CHANGELOG.md  pyproject.toml
└── .github/workflows/ci.yml  lint + 测试 + 合规 + 打包
```

## 8. 测试

```bat
python -m pytest tests -q          :: 单元测试（无需 CubeMX）
python tests\test_standalone.py    :: 独立模式：把 MXMCP_CUBEMX_ROOT 指到不存在的目录
python tests\test_e2e.py           :: ~70 s，MCP 全流程（需 CubeMX）
python tests\test_advanced.py      :: 60+ 断言，覆盖新增命令族
python tests\test_rtos.py          :: RTOS 对象增删改与唯一名约束
python tests\test_middleware.py    :: 中间件启用与 active IP 报告
python tools\check_compliance.py   :: 确认没有 ST 派生文件进入仓库
```

实测（2026-10-29，Windows + CubeMX 6.15.0）：

| 脚本 | 结果 |
|---|---|
| `test_units.py` | 通过（含 913 文件真实生成） |
| `test_e2e.py` | 通过（F1 全流程、板卡工程、F4 时钟、CLI 桥） |
| `test_advanced.py` | **ALL OK**（93 工具时代） |
| `test_rtos.py` | 通过（任务/队列/信号量 + 重复名拒绝） |
| `test_middleware.py` | 通过（FREERTOS 集成 + verify） |
| `test_standalone.py` | 通过（无安装：建工程→引脚→生成 6 文件） |

## 9. 许可

MIT（见 [LICENSE](LICENSE)）。**注意**：仓库不含任何 ST 派生数据——
数据包与反编译产物由使用者从自己的安装件本地生成（`python -m mxmcp.bundle build`），
不随仓库或发行物分发。详见 [docs/OPEN_SOURCE.md](docs/OPEN_SOURCE.md)。
STM32 / STM32CubeMX 是 STMicroelectronics 的商标，本项目与其无隶属关系。

