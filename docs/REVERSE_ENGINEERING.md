# STM32CubeMX 6.15.0 — 逆向工程记录（最终版，含 CLI 全量实测）

目标：`C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX`（v6.15.0，DB.6.0.150）
目标产物：`mxmcp` —— 保留 CubeMX 全部能力（选型/引脚/时钟/外设/中间件/工程生成/包管理/代码导出）的 MCP 服务器。

---

## 1. 安装布局与运行机制

```
STM32CubeMX/
├── STM32CubeMX.exe        227 MB, PE32+ SFX：Stub + 内嵌 ZIP（内容同 jar）
├── STM32CubeMX.l4j.ini    启动器参数（trustStoreType=WINDOWS-ROOT 等）
├── jre/                   Temurin 21.0.3（含 javac/javap/jlink，非 jlink 裁剪版）
├── db/                    MCU/板卡/IP 数据库（XML + FTL 模板 + 图片）
├── plugins/               19 个功能插件 jar + ip/*.jar（45 个 IP UI 插件）
├── olddb/  help/  utilities/  Uninstaller/
└── .installationinformation   IzPack 安装元数据（含 Jenkins 构建路径、DB 版本、APP_VER=6.15.0）
```

关键结论：

* **不是 Excelsior JET，也不是 native-image**。EXE 是 PE stub + 完整 Java 应用容器：
  `java -jar STM32CubeMX.exe` 可直接运行（UM1718 亦如此记载），因此不需要脱壳，
  **插件 jar 与主应用 class 都是明文**，可直接 `javap`/反编译。
* 首次运行时 `java -jar` 在 EXE 内查找内嵌 ZIP；该 ZIP 的中央目录被截断/改写过
  （前几条记录的 name-length 比实际少 1 字节、size/CRC 置零、EOCD 被截掉），
  但**本地文件头完整**。`tools/dump_exe_zip.py` 用流式本地头解析重建出
  `_extract/cubemx_app.jar`（12 666 个条目，其中 `com/st/microxplorer/**` 242 个类）。
* 主应用依赖 `com.st.components.*`（CommandLineManager / ApplicationProperties 等），
  这些类**不在内嵌 jar 中**：启动日志显示它们由 EXE 引导层在运行期提供
  （`java -jar` 仍能解析，说明它们在 EXE 的非 ZIP 区域/引导类路径中）。
  影响：无法从 jar 静态读取 CommandLineManager 源码，改为**运行期行为采集**（见 §3）。
* 日志：`%USERPROFILE%/.stm32cubemx/STM32CubeMX.log`，并由 log4j2 配置
  `log4j/log4j2.stm32cubemx.xml` 同时输出到 stdout —— 这就是 CLI 的抓取通道。
* 用户目录：`~/.stm32cubemx/`（偏好、第三方 pdsc、log4j 配置）、`~/.stmcufinder/`、
  `~/STM32Cube/Repository/`（固件包；本机已装 `STM32Cube_FW_F1_V1.8.0` 与若干 X-CUBE pdsc）。

## 2. 功能面（必须 1:1 保留）

| 领域 | 实现载体 |
|---|---|
| MCU 选型 / 引脚复用 / 冲突校验 | `db/mcu/*.xml`（5 960 文件）+ 主应用 `mc/mcu` 包 + `ip/*.jar` |
| 时钟树 | `plugins/clock.jar` + `db/mcu/config/RCC-*_Configs.xml` |
| 外设与中间件配置 | `plugins/ip/*.jar`、`db/mcu/IP/*_Cube_Modes.xml` |
| 工程生成（C 代码 + IDE 工程） | `plugins/projectmanager.jar`、`filemanager.jar`、`db/templates/*.ftl`（Freemarker） |
| 软件包管理（Cube FW / CMSIS-Pack） | `plugins/updater.jar`、`thirdparty.jar`、`db/plugins/updater/*.xml` |
| 板卡支持 | `db/plugins/boardmanager`、`loadboard` 命令 |
| 功耗计算 / LPBAM / DDR / RIF / CAD | `power.jar`、`lpbam.jar`、`ddr.jar`、`rif.jar`、`cadmodel.jar` |
| 模板自定义生成 | `set tpl_path`/`dest_path` + GraalJS（jar 内含 truffle/js，`-s` 脚本模式即用其执行） |

**结论：不要重写引擎。** MCP 作为**受控前端**驱动官方引擎（`java -jar STM32CubeMX.exe -q <script>`），
所有能力都经由 CubeMX 自身命令语言执行，天然保真（引脚合法性、时钟求解、代码模板全部由 ST 引擎完成）。

## 3. CLI 命令语言（已由运行期采证）

三种模式：

* `-i`：交互式 `MX>` 提示符
* `-s <file>`：带 UI 执行脚本
* `-q <file>`：无 UI（headless）执行脚本 ← MCP 使用此模式（另有 `-expMode`，跳过 splash）

命令族（`help` 输出，全部为一级命令；子命令用空格分隔）：

```
help exit script exit_mx set get reset add check csv generate list import export
lock unset pinout disable load loadboard tinyload waitclock switch
project setDriver SetStructure SetCopyLibrary config swmgr pack dma NVIC clock
cpload cpexport login logout login_with_gui updateIpUI tooltip simulate
isPluginError user_analytics log setprop getprop getenv xcopy xts xtest xbuild
popupwrapper xcubedl MultiConfig ocxtest possible_value not_a_possible_value
```

### 3.1 实测确认的核心语义

| 命令 | 语义 | 备注 |
|---|---|---|
| `load <mcu>` | 新建该 MCU 工程（清空当前配置） | `load STM32F103C8Tx` |
| `config load <ioc>` | 载入 .ioc | 载入后 `get mcu name` 返回归一化名 `STM32F103C(8-B)Tx` |
| `config saveas <name>` | 保存为新工程 | **实际写到 `<project path>/<basename>/<basename>.ioc`**；未设 `project path` 时写 `%CD%` |
| `config save` | 保存当前工程 | 指向未初始化路径时**挂起（无输出）**，不可在 headless 中盲用 |
| `config saveext` | 保存含默认值的完整配置 | |
| `project path/name/toolchain` | 工程生成目标 | `project path` 会立刻创建 `Untitled/Untitled.ioc` |
| `project generate` | 生成完整工程（含固件库与 IDE 工程） | 实测 21 s 产出 Core/Drivers/MDK-ARM 等 |
| `generate code <dir>` | 只生成 MX 代码（不含库/IDE 工程） | |
| `generate all_code_in_main` / `one_file_per_ip` | 生成布局 | 等价 `project couplefilesbyip 0/1` |
| `set pin <pin> <signal>` | 绑定引脚功能 | 信号名来自 `get functions <pin>`（如 `USART1_TX`、`RCC_OSC_IN`） |
| `set mode <IP> "<Mode>"` | 设置外设模式 | 模式名来自 `get modes <IP>`；**必须加引号**才可靠 |
| `set ip parameters <IP> <param> <value>` | 设置 IP 参数 | 参数名用 `.` 任意键名也能写入（见下） |
| `set ip parameters <IP> IPParameters a,b,c` | **把参数登记进 .ioc 的 `IPParameters` 清单** | 关键技巧：不登记则参数只留在内存、不落盘 |
| `get ip parameters <IP> <param>` | 读回 | 未登记时返回 `=null` / `is not set` |
| `get functions <pin>` / `get pinout` / `get signal <pin>` | 引脚/功能查询 | `get pinout` 输出 `pin: signal` |
| `get modes/mapped/available/mode/...` | 外设模式查询 | |
| `set gpio parameters <pin> <param> <value>` | GPIO 参数 | **pin 必须用完整名**（`PC13-TAMPER-RTC`）；`PC13` 返回 KO |
| `reset pin/signal/mode/...`、`lock pin`、`clearpinout` | 撤销与锁定 | |
| `check mode enabled <IP> "<Mode>"` / `check mcu modes` | 合法性检查 | |
| `NVIC enable|disable|set_priority|set_subpriority|set_prioritygroup` | 中断配置 | 由 `export script` 实录得到 |
| `export script <file>` | **把当前配置序列化成可重放 CLI 脚本** | 逆向捷径：任意 .ioc 都能变成命令序列 |
| `csv pinout <file>` | 引脚表导出 | |
| `loadboard <board> <allmodes|nomode>` | 板卡工程 | |
| `swmgr refresh|install|remove|set repository|connection status` | 固件包管理 | |
| `pack enable|disable|status|validate|context|migrate` | CMSIS-Pack 组件 | |
| `project compiler GCC|Starm-Clang`、`SetStructure Advanced|Basic`、`SetCopyLibrary ...` | 工程选项 | |
| `setprop/getprop/getenv`、`login/logout`、`simulate cubeIDE`、`MultiConfig ...`、`xcubedl`、`xcopy`、`xbuild` | 其余能力 | |

### 3.2 采证方法

* `tools/run_cmds.py`：把命令行喂给 `-q`，抓 stdout（cube 的 log4j stdout channel），
  过滤 `[INFO]` 行得到纯 CLI 应答（`OK`/`KO`/数据）。
* `tools/collect_help.py`：对每个命令族执行 `<cmd>`/`help <cmd>`，落盘 `docs/cli_help/*.txt`。
* `tools/dump_all_commands.py`：对 `plugins/**` 全部 class 做 `addCommand` 常量池扫描 + `javap`
  反编译，抽出 89 条注册字符串（含 `pack enable`、`NVIC`、`clock resolution`、`dpm` 等隐藏族）。
* `tools/mx_harness.py`：Python 侧最小驱动器（MCP 会话引擎原型）。

### 3.3 关键坑位（已解决）

1. **`config save` 在 headless 下挂起** → 只用 `config saveas`，并预先 `project path`。
2. **`-q` 模式仍会初始化 Swing/JxBrowser** → 每次启动约 6–17 s；MCP 必须常驻会话
   （交互式 `-i` 的 stdin/stdout 通道），一次性冷启动太慢。
3. **参数不登记不落盘** → 见 `IPParameters` 技巧；这同时解决时钟树：RCC 的
   `AHBFreq_Value/PLLMUL/SYSCLKSource/APB1CLKDivider/...` 全部可从 `.ioc` 复核。
4. **输出目录语义**：`config saveas`/工程生成都相对 `project path`，MCP 需要强制绝对化并回传真实路径。
5. **`.ioc` 是唯一权威状态**：`config saveext` + `IPParameters` 让内存态完整落盘，
   因此 MCP 的“读状态”应当读 `.ioc`，“改状态”走 CLI + 重存，二者可交叉校验。

## 4. 数据库资源（用于离线查询工具）

* `db/mcu/*.xml`：每颗 MCU 一份（引脚、封装、IP 实例、复位态、alternate 映射）
* `db/mcu/families.xml`、`rules.xml`、`compatibility.xml`、`defines/defines`
* `db/mcu/IP/*_Cube_Modes.xml`：IP 模式树；`db/mcu/config/*_Configs.xml`：模式/参数/时钟约束
* `db/plugins/boardmanager`、`db/plugins/mcufinder/mcu/cube-finder-db.zip`（42 MB 选型库）
* `db/templates/*.ftl`（Freemarker 代码模板，约 700 个）、`db/plugins/projectmanager/*.ftl`（工程文件模板）
* `db/plugins/power/*.xml|json`（功耗模型与 RF/SubGHz 场景）

## 5. 交付产物

```
mxmcp/
├── mxmcp/
│   ├── server.py        MCP 入口（stdio JSON-RPC 2.0；--selftest/--call/--list-tools）
│   ├── rpc.py           协议层（initialize / tools/list / tools/call / resources）
│   ├── engine.py        引擎（-i 常驻会话；超时杀进程；prompt 粘行剥离）
│   ├── store.py         工程池、保存/重载、MCU 料号→RefName 解析、固件路径
│   ├── ioc.py           .ioc 读写、IPParameters 视图、结构 diff
│   ├── catalog.py       本地 db 索引（2016 MCU / 215 板卡 / 687 IP 模式 / 656 模板）
│   ├── firmware.py      固件包完整性扫描（package.xml + Drivers）
│   └── tools_*.py       工程 / 选型 / 引脚外设 / 时钟 / 生成 / 软件包 / CLI 兜底
├── tests/               test_units.py（20 项断言）+ test_e2e.py（MCP 全流程）
├── docs/                本文件、CLI_REFERENCE.md、VALIDATION.md、cli_commands.tsv、javap 转储
└── tools/               逆向与探针脚本（复现证据，不是运行时依赖）
```

## 6. 二期修正（实测后推翻的早期判断）

| 早期判断 | 实测更正 |
|---|---|
| `set gpio parameters <pin>` 不可用，只能用 `.ioc` 直写 | **可用**：pin 必须是 MCU 完整名（`PC13-TAMPER-RTC`），短名 `PC13` 才返回 KO |
| `pack enable` 只是语法问题 | 需 `TP_ADVANCED_MODE=on` + 已下载的第三方包；built-in peripheral pack 处于 `isIntegrated()==true` 状态，永不可选 |
| `project generate` 慢/不稳定 | 只要固件包版本与 `.ioc` 的 `FirmwarePackage` 一致就稳定在 5 s；不一致会进入联网下载（无 UI 下挂起） |
| 时钟树一次写入即生效 | 新工程首次写入只登记参数，推导值要在保存+重新载入后再写一轮才更新（F1）；已求解工程单轮即可 |
| `-q` 批处理足够 | `-q` 每次冷启动 6–17 s，且部分命令会弹窗/联网挂起；必须常驻 `-i` + 超时重启 |


