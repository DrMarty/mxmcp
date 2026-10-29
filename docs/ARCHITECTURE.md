# STM32CubeMX 6.15.0 — 全量架构逆向

证据来源：本机安装 `C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX`
（1 137 8 文件 / 1 520 MB / 709 目录），产物 SHA-256
`67b12576eed1c9544668b529458d87e6a9db600cf53492da1534afa8cf1ca0b8`。
所有数字都由 `tools/*.py` 与 REA 从安装件里直接抽取，`analysis/*.json` 为原始记录。

---

## 0. 分层总览

```
STM32CubeMX.exe   PE32(i386) Launch4j 装载器 + 内嵌 ZIP（同一文件即 jar）
  └─ 内嵌 ZIP：起始 0x13000，中央目录 0xD2F0A03，54 774 条目
       ├─ com/st/components/**        框架层：CommandLineManager、pdscmanager、JxBrowserEngine、swing、net
       ├─ com/st/microxplorer/**      主程序：mcu 模型、codegenerator、db、mcufinder、plugins.*
       ├─ com/st/ipmodeconfigmanager  IP 模式/配置 XML 引擎（104 类）
       ├─ org/graalvm|com/oracle/truffle  GraalJS（脚本/校验表达式）
       ├─ com/teamdev/jxbrowser       Chromium 内核（首次运行解包到 ~/.jxbrowser-8.5.0）
       └─ 第三方库：poi/xmlbeans、apache ant、jfree、bouncycastle、lowagie(iText)、jackson…
  ├─ plugins/*.jar   19 个功能插件（clock/power/projectmanager/thirdparty/analytics…）
  ├─ plugins/ip/*.jar 45 个 IP 配置插件（adc/can/i2c/freertos/usbx…）
  ├─ db/             数据资产（XML 6 775 / FTL 1 756 / IOC 504 / LD 277 / DTSI 75…）
  ├─ third_parties_plugins/  STM32CubeIDE-MX-services（Eclipse p2 仓库，20 plugin + 34 feature）
  │                          + com.st.stm32cube.ide.common.services.mx.jar-1.19.0-b1.jar（62 MB）
  ├─ utilities/      STM32PackCreator.jar（4 823 类）、TrustedPackageCreator.jar
  └─ Uninstaller/    IzPack 卸载器（uninstaller.jar 1 117 类）
```

类/方法规模（`analysis/api_index.json`，只统计 `com.st.**` 顶层类）：
**3 222 个类 / 41 841 个方法 / 38 255 个字段 / 339 个包**。

| 包 | 类 | 方法 | 作用 |
|---|---|---|---|
| `com.st.microxplorer.mcu` | 67 | 3 430 | MCU/IP/引脚/中断对象模型，CLI 命令宿主（Mcu、NVICService、DMAService、MDMAService、GicService、Constraints…） |
| `com.st.microxplorer.codegenerator` | 43 | 1 401 | C 代码生成主引擎（FreeMarker 驱动） |
| `...plugins.projectmanager.gui` | 70 | 1 102 | 工程管理页（工具链、备份、报告） |
| `com.st.microxplorer.mcufinder.db` | 24 | 1 056 | 选型数据库（SQLite + 交叉选择） |
| `...plugins.projectmanager.model` | 14 | 1 004 | `.ioc` 键值模型 |
| `...mcu.memorymap` | 32 | 702 | MMT 内存映射工具 |
| `...plugins.projectmanager.engine` | 18 | 646 | 生成调度（IDE 服务、文件复制） |
| `...plugins.thirdparty.model` | 36 | 630 | CMSIS-Pack/中间件模型 |
| `com.st.ipmodeconfigmanager.xmlManager.ipconfig` | 22 | 620 | `*_Configs.xml` 解析 |
| `...projectmanager.security[.reader]` | 76 | 1 074 | H5/H7RS 安全启动/TrustZone/OTFDEC/IOPMP 配置 |
| `...plugins.risaf` | 54 | 567 | RISAF 资源安全隔离 |
| `...mcufinder.db.crossselector` | 38 | 505 | 交叉选择（比价/替代料，Ultralibrarian） |

---

## 1. 原生装载器（EXE 本体）

由 REA 的 PE 解析器给出（`evidence ev_77654766…`、`ev_cb53c303…`、`ev_18f9bfe0…`）：

| 事实 | 值 |
|---|---|
| 格式 | **PE32（i386，machine 332）**，不是 PE32+；无 TLS 目录、无 LOAD_CONFIG |
| 导入表 | 5 个 DLL / 88 个函数，imphash `6011984d7c1f1b97a34d7517a498bff8` |
| 关键导入 | `RegOpenKeyExA/RegQueryValueExA/RegEnumKeyExA`（找 JRE）、`CreateProcessA`（起 JVM）、`FindResourceExA/LoadResource/LockResource`（读内嵌资源）、`CreateMutexA/WaitForSingleObject`（单实例）、`GlobalMemoryStatusEx`（算 `-Xmx`）、`SetEnvironmentVariableA`、`MessageBoxA/CreateWindowExA/LoadImageA/SetTimer`（启动 splash）、`ShellExecuteA`（开链接） |
| 资源 | `RT_ICON` 8 个尺寸（16/20/24/32/48/64/128 + 一个变体）、`RT_GROUP_ICON`、`RT_VERSION`(772 B)、`RT_MANIFEST`(id 24) |
| 版本信息 | FileDescription `MicroXplorer for STM32Cube`，InternalName/ProductName `STM32CubeMX`，**FileVersion/ProductVersion `6.15.0-RC4`**，LegalCopyright `STMicroelectronics`；stub 自身 `0.1.0.4`（Launch4j） |
| Authenticode | 签名者 **STMicroelectronics International N.V.**（CH，DigiCert Trusted G4 Code Signing RSA4096 SHA384 2021 CA1，序列 `0b12c8b575d0d6e16489812ce64cd7c5`，有效期 2022-10-26→2025-10-25），带 DigiCert Timestamp 2024 时间戳；PKCS#7 内含 5 张证书。*只做了结构解码，未验证链与摘要覆盖* |

结论：**没有加壳、没有脱壳需求**。`java -jar STM32CubeMX.exe` 直接可用（JVM 的 ZIP 读取器按中央目录定位），UM1718 也如此记载。

### 内嵌归档的真实结构

| 项 | 值 | 说明 |
|---|---|---|
| 本地文件头起点 | `0x13000`（= 条目 0 的 local_header 偏移 0） | 由 `META-INF/MANIFEST.MF` 的 local header 反推 |
| 中央目录 | `0xD2F0A03`，标准 46 字节记录 | **早期判断"中央目录被截断/CRC 置零"是错的**：那是字段偏移读错（crc@16、csize@20、usize@24、nlen@28）造成的假象 |
| 条目总数 | **54 774** | 早期流式扫描只拿到 12 666，因为遇到第一个不以 `PK\x03\x04` 开头的字节就停了 |
| 完整重建 | `_extract/cubemx_full.jar`，227 113 372 字节，`ok=54774 bad=0` | `tools/rebuild_full_jar.py` |
| 组成 | truffle 8 138 / jxbrowser 7 185 / icu 5 453 / openxml 3 633 / **microxplorer 3 368** / commons 2 852 / poi 2 769 … | `analysis/cd_entries.json` |

重要更正：**`com/st/components/**` 确实在内嵌 jar 里（196 条目）**，包括
`com.st.components.util.CommandLineManager`。前一版结论"由 EXE 引导层提供、无法静态读取"
来自那份不完整的 12 666 条目提取，现已直接反编译（见 §3）。

---

## 2. 启动序列（日志实证）

```
Launch4j: 注册表/环境找 java → 组装 -Xmx（GlobalMemoryStatusEx）→ CreateProcessA
          java -jar <exe 自身> [-i|-s|-q]
JVM     : 载入内嵌 jar（MANIFEST Class-Path 指向 plugins/*.jar）
MicroXplorer: 选 DB（olddb/db → DB.6.0.150）→ 注册 21 个插件
             → MainPanel/TabSelector/ProjectManagerView
             → RtosApiDefinition(rtos_apis.xml) → GPIO 约束/通道约束
             → updater.jar：注册 4 个 UpdaterGuiPlugin + CMSIS pack repo
             → thirdparty：ThirdParty 目录 + .stmcufinder/plugins
             → 首次运行：JxBrowser Chromium 134.0.6998.89 解包到 ~/.jxbrowser-8.5.0
             → McuFinder 载入 cube-finder-db.db + React 客户端
冷启动耗时 15–18 s（headless -q/-i 均如此）
```

日志级别由 `~/.stm32cubemx/log4j2.xml` 控制（`MX_STDOUT` appender + `STM32CubeMX.log`），
`-Dorg.apache.logging.log4j.simplelog.level=TRACE` 会把 DEBUG 全打出来（曾用于取证，
配置文件已恢复出厂）。

---

## 3. CLI 框架（`com.st.components.util.CommandLineManager`）

反编译事实：

* 内部维护 `List<CommandLine>`；`addCommand(String name, String help, int argc, CommandLineListener l)`
  → `addUnique(...)`：`CommandLine(name, help, argc, listener, boolean)`，重名以
  `equalsIgnoreCase` 判重（第一条胜出）。
* 命令匹配按 **整串前缀**（大小写不敏感），所以 `get ip parameters RCC BaudRate`
  会优先匹配最长注册串；argc 决定剩余参数如何切分。
* 交互协议：提示符 `MX> `（**无换行**），应答终止符 `^\s*(\d+)\s+(OK|KO)\s*$`；
  无输出命令把提示符粘在下一条应答前面；少数服务把结果写在 **log4j 行**里
  （`dma/NVIC/MMT/get mode_param_pattern`），并且存在把 `0 OK` 直接粘在正文尾部的写法
  ——`mxmcp/engine.py` 同时处理这三种成帧。
* 89 条 **根命令**、`help` 只打印全局表（`help <cmd>` 不回显子命令），子命令用法要
  靠"裸命令回显"取得——这就是 `cli`/`cli_batch` 必须暴露的原因。
* 动态命名：`NVICService.initCommands()` 用
  `getInstanceName()+"<verb>"`（`makeConcatWithConstants`）注册
  `<IP> enable|disable|set_priority|set_subpriority|set_prioritygroup|…`，
  因此按实例名（NVIC/GIC/DMA…）生成命令，静态常量池看不到完整名字。

### 完整注册表

`analysis/cli_registry.json` / [docs/CLI_REGISTRY.md](CLI_REGISTRY.md)：
**267 条唯一注册**，覆盖 14 个 jar、64 个命令头。此前版本记录的 89 条只是主面板可见族。
新登记的家族（含 argc 与 help 原文）：

| 家族 | 条数 | 代表命令 |
|---|---|---|
| `dma` | 18 | `available_controller_streams`、`is_available_in`、`set_flow`、`listbriefly`、`used_flows` |
| `mdma` | 10 | `list_peripheral_requests`、`add_channel_request`、`list_request_channels` |
| `gic` | 7 | `get_enable_state`、`set_triggering_mode`、`set_security` |
| `MMT` | 9 | `dump free|AppReg|HRange|HRegion`、`reserved (HW|SW) "…"`、`load/save pre-config`、`ThreadX y/n` |
| `selector`/`boardselector`/`exampleselector` | 8/7/13 | `list mcus`、`list columns`、`set filter`、`set peripheral <n> <v>` |
| `import` | 10 | `try auto import`、`get report`、`add compatibility_rule`、`set manual import_option`、`hackmxdb` |
| `MultiConfig` | 6 | LPBAM 上下文增删改选 |
| `cpload`/`cpexport` | 3 | 两个 `.ioc` 并排比较并导出报告 |
| 其他 | `possible_value/not_a_possible_value ip parameters`、`get sub-mode(s|-state)`、`get mode_param_pattern`、`bootpath wizard`、`generate deviceTree`、`add mw`、`xts/xtest/xbuild/xcopy`、`tooltip log on/off`、`updateIpUI`、`isPluginError`、`simulate cubeIDE`、`user_analytics` |

---

## 4. 插件契约

`com.st.microxplorer.plugin.PluginView`（抽象类，实现 `IPluginView`+`PluginViewConstants`）：

* 生命周期：`setParent/setUserPreferencesHandler/setApplicationInformation/setTabIndex`
  → `activatePlugin/deactivatePlugin` → `loadConfig(String)/saveConfig(String)`
  → `importConfig` → `exit`。
* UI 注入：`addToToolBar(IPluginToolBar)`、`addToMenuBar(IPluginMenuBar)`、
  `addToOutputTab(JTabbedPane)`、`getUI()`、`isVisible()`、`resize()`、
  `skipToError(String)`、`getTooltipText()`。
* 报告：`generatePdfReport(com.lowagie.text.Document, int)`、
  `generateTextReport(PrintWriter)`。
* **生成**：`HashMap<String, HashMap<String,String>> generateCode(String, IProgressBarMonitor)`
  ＋ `setSpecificCodeInputs()`。
* **RPC**：`Object getSpecificTask(int opcode, Object payload)`。
  `PluginViewConstants` 提供 **217 个 opcode + 30 个返回码 + 99 个字符串常量**
  （`analysis/plugin_protocol.json`），按子系统分组：
  `ANALYTICS(16)`、`FileManager(23)`、`Pinout(13)`、`ProjectManager(41)`、
  `Updater(51)`、`ThirdParty*(数十)`、`IPManager(5)`、`Clock(1)`、`PCC(2)`…
  Updater 返回码表（`ReturnFound/ReturnBusy/ReturnErrorBadMD5/…`）就是
  下载状态机的错误枚举，`swmgr install` 的失败信息直接来自它。
* 宿主接口：`IPluginApplicationInformation`（版本/图标/debug/DB 访问器）、
  `IPluginMainPanel`（isMcuLoaded/isModified/showPluginView/printMessage/setPluginError…）、
  `IPluginUserPreferences`（登录、代理、仓库路径、数据刷新策略）、
  `IPluginDBAccessor`（新旧 DB 路径与版本）、`IPluginMenuBar/RibbonBar/ToolBar`、
  `IPluginColorsManager`。
* 19 个功能插件 + 45 个 IP 插件；IP 插件通过
  `ip/*.jar` 内 `IPPluginView` 子类 + `db/mcu/IP/*_Cube_Modes.xml` 协作。

---

## 5. 代码生成链路

1. `CodeGenerator`（43 类 / 1 401 方法）收集每个 IP 的 `generateCode` 结果
   （`include/init/deinit/MSP/回调` 分类的 map）。
2. FreeMarker：安装内 **1 756 个 `.ftl`**
   （`db/templates` 1 733 + `db/plugins/projectmanager` 20 + PackCreator 3）。
   `analysis/template_model.json` 提取了 **2 706 个模型键**、插值计数、
   include 图与每模板键分布；高频键如
   `definition / argument / characteristic / used_api / method / instanceIndex /
   IpInstance / ipName / FamilyName / Configuration / clock / BoardName / filesName /
   fwVersion / SERVICE_SHORT_NAME_UpperCase / SvcNbr`。
3. 命名约定可见于模板引用：`tpl_makefile_v1-0.ftl`、`tpl_dts-v1_kernel_v1-0_dts.ftl`、
   `*_c.ftl` / `*_h.ftl`（成对的 .c/.h 模板）。
4. IDE 工程（STM32CubeIDE / Makefile / CMake）由 **CubeIDE-MX-services** 完成：
   CubeMX 先写 **mxScratch**（schema `mxScratch_v30.xsd`，根元素含
   `startup / sourceEntries / optimization / memory / memories / lib / include / icfloc …`），
   再以 `--service <name>` 方式在同一 JVM 内调用 p2 池中的服务：
   `check / cleanup / projectSetup / projectUpdate / buildSetup / buildUpdate /
   updateScopeFinder / resourcesSetup / startupSetup / lnkSetup / lnkUpdate /
   dtSetup / threadSafeSetup / threadSafeUpdate / debugSetup / debugUpdate /
   projectRootModeSetup`（`analysis/cubeide_services.json`，28 个服务类、6 个消息包）。
   linker 脚本来自 `linkerdb`/`linker` 插件（安装内 277 个 `.ld`），
   设备树来自 `dtSetup` + `db` 内 75 个 `.dtsi`/59 个 `.dts`。
5. 链接器/工具链：`com.st.stm32cube.ide.*` 通过 `com.sun.jna`（p2 池内）调用本机工具。

---

## 6. 数据资产（`db/`）

`analysis/db_schema.json` + `analysis/db_census.json`（171 个目录）：

| 资产 | 数量 | 结构要点 |
|---|---|---|
| `db/mcu/*.xml` | 2 019 | 根 `Mcu`：`RefName/Name/PackageName/RPN/Visible/ClockTree/DBVersion/Family`；子元素 `Core/Flash/Ram/IONb/Frequency/Voltage/Temperature/Current/E2prom/Peripheral/Signal/IP/Pin`。`Peripheral@Type/MaxOccurs`、`IP@InstanceName/Name/Version/ConfigFile/ClockEnableMode`、`Pin@Name/Position/Type/Variant`、`Signal@Name/IOModes` |
| `families.xml` | 1 | `Family@Name`(27) / `SubFamily@Name`(125)，共 2 711 个 `Mcu` 条目（含变体，去重后 2 016 颗） |
| `db/mcu/IP/*_Modes.xml` | 1 321 | `IP@Name/IPType/Version/DBVersion` → `Mode/RefMode(Abstract,BaseMode)/Parameter/RefParameter/Signal/RefSignal(IOMode,ShareableGroupName,Virtual)/ModeLogicOperator/SignalLogicalOp/ConfigForMode/Semaphore/PossibleValue/Condition/Description/About` |
| `db/mcu/config/*_Configs.xml` | 1 308 | `RefConfig/CallLibMethod(ReturnHAL)/LibMethod/MethodArg(ParameterName)/Argument(AddressOf,GenericType,TypeName,Context,OptimizationCondition)/IFCondition(Expression)/ImplementCallBack/File(Category,Name)/RefComponent(Cclass,Cgroup,Cversion)/HardCode(Text)` |
| `db/mcu/memory` | 47 | 根 `rzone`（H7RS/U5 系列内存区） |
| `db/mcu/packs/*.vpdsc` | 19 | CMSIS-Pack 描述（`package`） |
| `db/contextual` | 364 | `ctx_periph_help / ctx_core_help / ctx_pinout_help`（GUI 上下文帮助） |
| `db/plugins/boardmanager` | 215 pdsc + 430 ioc | 板卡（`bsp/`、`boards/`） |
| `db/plugins/clock` | 64 | `Clock` 树定义 |
| `db/plugins/power` | 225 xml + json | `Battery/Consumption`、`rf/ble.json`、`subghz/tx_subghz.json` |
| `db/plugins/updater` | 4 | `STMUpdaterDefinitions.xml`（`SiteAccess Url=https://sw-center.st.com SiteRoot=/packs/resource/`、`SoftUpdates SiteSubPath=library/`、每个 `PackDescription Release/ReleaseSize/ReleaseMD5/Status` + `OS Type=win|mac|lin` + `DataBaseRelease ReleaseMax=DB.6.0.150`）、`updaterThirdParties.xml`（第三方 `.pack` 直链 + `PackDependencies`）、`PacksControlFlags.xml`（**Denied 列表**，如 Keil DFP）、`cubemx.pidx` |
| `db/plugins/projectmanager` | 2 | `project.xml`、拼写错误的 `Toulchains.xml` |
| `db/plugins/mcufinder` | — | React 前端 `reactClient/`、`reactClient1/`、`images/packages/*_top.png` |
| `db/templates` | 1 756 ftl | 见 §5 |

### 6.1 条件表达式语言（`analysis/condition_language.json`）

* **636 975** 条 `Condition@Expression`（2 629 文件，0 解析失败）。
* 词法：`&`、`|`、`!`、`=`、`>`、`<`、括号；标识符 = 参数名/模式名/信号名。
* 特殊引用：`$IpNumber`、`$IpInstance`、`$IpInstanceCH0…CH12`、`$context`、
  `Semaphore_<name>$IpInstance`（如 `Semaphore_output_Channel$IpInstance`）、
  die 变量（`DIE483`、`DIE413`）、`true`；函数 `MOD(...)`、`IF(...)`。
* 安全类前缀在 H5/H7RS 大量出现：`S_SECURE`、`GTZC_S`、`FLASH_BB_PRIV/SEC`、
  `OB_BOOT_LOCK_ENABLE`、`OB_RDP_LEVEL_0`、`OB_DUALBANK_DUAL`。
* `RefParameter@Type` 实际取值集合（含手写拼写错误，构成事实清单）：
  `list(132 600) / string(52 947) / integer(36 605) / double / hex / boolean / String /
  stringRW(5 536) / integerReadOnly(1 458) / uniqueElementList(1 824) /
  UniqueElementList(1 725) / Array / List / StringRW / StringW / RWString / RWstring /
  decimal / subtitle / polynomial / polynomialOdd / polynomialodd / StringHex /
  doubleReadOnly / doubeReadOnly / IntregerReadOnly / interger / intger / u8niqueElementList / Integer / Hex / Int / bool / int …`
* `PossibleValue@Action`：`Disable(51 083) / DISABLE(2 036) / Remove(3 705) /
  ENABLE(1 251) / remove(1 165) / disable(339)`，另有把外设名写进 Action 的
  历史用法（`XSPI1/XSPI2/SDMMC1/SDMMC2`）。
* `Group`/`Unit` 词表：`REGISTERS`、`BB Pages`、`NOR/PSRAM timing`、
  `Advanced Parameters`…；单位 `MHz/KHz/Hz/ns/Bytes/Bits/s/V/Byte(s)`。
* 条件最多的 IP：`UART/TIM/ETH/flash/RCC/SMARTCARD/USART/SPI/FDCAN/RTC`。

> MCP 的 `ip_param_get/ip_param_set` 只改值，**合法性判定交给引擎**
> （`value_check` 工具直接调用 `possible_value`/`not_a_possible_value`），
> 因为这套表达式还依赖 die/semaphore/context 运行时状态。

### 6.2 `.ioc` 语法（`analysis/ioc_grammar.json`）

506 个真实 `.ioc`（215×2 板卡 + 用户工程 + 生成样本）统计出 **7 670 个键模式**：

* 头部固定：`File.Version=6`、`Mcu.Family/Name/Package/PinsNb/IPNb`、
  `KeepUserPlacement=false`、`CAD.formats/CAD.pinconfig/CAD.provider`、
  `MxCube.Version`、`MxDb.Version`、`PB.ProgrammerPrivileges` 等。
* 索引列表：`Mcu.Pin0…Mcu.PinN`（30 896 次）、`Mcu.IP0…`（4 704 次）、
  `Mcu.PinsNb`/`Mcu.IPNb` 为计数；值域是 **完整引脚名**（`PC13-TAMPER-RTC`、
  `PD0-OSC_IN`、`VP_<IP>_<Signal>`）。
* 引脚属性（按模式出现）：`PIN.Signal`(30 289) `PIN.Locked`(27 887)
  `PIN.GPIOParameters`(25 354) `PIN.GPIO_Label`(23 013) `PIN.Mode`(10 534)
  `PIN.PinAttribute`(5 908) `PIN.GPIO_PuPd/GPIO_Speed/GPIO_Mode`。
* IP 属性：`<IP>.IPParameters` 登记清单决定其余键是否持久化；
  `RCC.`(28 555) 为最大命名空间，其次 `RIF.`(20 668)、`SH.`(16 937，FMC/OSPI 引脚复用)、
  `NVIC.`(3 924)、`PCC.`(1 977)。
* 转义：值内 `:` 写成 `\:`；`NVIC.<IRQ>` 键自身含 `:` 语义（如
  `NVIC.USART1_IRQn,0,true:ENABLE,1,`）。
* `ProjectManager.*` 全量键（工具链、`FirmwarePackage`、`CustomerFirmwarePackage`、
  `functionlistsort`、堆栈、`BackupFolder`、`KeepUserCode`、`UAScriptBefore/After` …）
  见 `mxmcp/ioc.py` 的读写实现与 `project_options` 工具。

---

## 7. 运行时持久状态

| 位置 | 内容 |
|---|---|
| `~/.stm32cubemx/` | `log4j2.xml`（console+file）、`STM32CubeMX.log`、`cad_preferences.json`、`mxinstallversion.txt`、`favorites.mcus.txt` / `favorites.boards.txt`、`ThirdParty.prefs`、`db.json`、`.jxbrowser-8.5.0/Chromium/`（首次运行解包的 Chromium 134.0.6998.89，含 `.sig` 与 `extraction.lock`） |
| `~/.stmcufinder/plugins/mcu/` | `cube-finder-db.db`（86 MB SQLite，**19 张表**）、`cube-finder-db.zip`(43 MB)、`api_config.json`、`mcuFinder.mfd`、`md5.xml`、`tutoVideoDB.json/.zip`、`mcusAds.json`、`additional_hw_images/*.jpg` |
| `~/STM32Cube/Repository/` | 固件包目录 `STM32Cube_FW_<FAM>_V<x.y.z>`（完整性判据：`package.xml` + `Drivers/`）；本机仅 `FW_F1_V1.8.0` 完整（`Release="FW.F1.1.8.0" Patch="FW.F1.1.8.6"`） |
| 注册表 | `HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\STM32CubeMX`（IzPack）、`...\App Paths\STM32CubeProgrammer.exe`（含 Wow6432Node）用于定位 `STM32_Programmer_CLI` |
| 工程目录 | `.ioc`、`project_ext.ioc`（`*.Ext` 补全值）、`.mxproject`、`mxcube_log.txt` |

**选型数据库结构**（`analysis/mcufinder_data_layer.json`，只读 SQLite）：
`attribute(232)`、`cpn(17 491)`、`cpn_has_attribute(644 828)`、`cpn_relates_to_cpn`、
`feature(1 807)`、`featureitem(5 482)`、`prmis_class(30)`、
`prmis_class_has_attribute(514)`、`resource(2 766)`、`rpn(14 550)`、
`rpn_has_attribute(143 130)` … —— 典型 EAV：商业型号(CPN)/订购号(RPN)/属性/资源/特性。
MCP 通过 `product_db` 工具直接查询（读模式，不写）。

**React↔Java 桥**（`analysis/jxbrowser_bridge.json`）：前端只暴露 3 个
`window.java.*` 回调（`getCustomPinsAsString`、`getOnlyCustomPinsAsString`、
`getStandardPinsAsString`），即"从选型页导出引脚分配"路径；其余数据走本地
`cube-finder-db.db` 与 `ApiDb/DbMcus/DbBoards/DbExamplesSqlite` Java 层，
外部仅有 `api.ultralibrarian.com/api/v1`（比价）与 `cdn.jsdelivr.net`（样式）。

---

## 8. 网络与授权面

| 端点 | 用途 |
|---|---|
| `https://sw-center.st.com/packs/resource/`，`library/` 子路径 | 固件/DB/MX 自身更新（`STMUpdaterDefinitions.xml`），下载校验用 `md5.xml` |
| `https://sw-center.st.com/packs/cube-finder-db/md5.xml`、`/packs/cubeanalytics/` | 选型库与分析包 |
| `https://my.st.com/cas/login`（含 `?service=`） | CAS 登录 |
| `https://stm32cube-ua.st.com/api/user_service/login/callback?code=` | OAuth 回调（userauth） |
| `https://mcucrossselector.codex.cro.st.com`、`xsel.stmcufinder.com`、`https://artifacts.st.com:443/artifactory/mcd-cubemx-maven-local/` | 交叉选择 / 构件 |
| `https://api.ultralibrarian.com/api/v1` | 价格与替代料 |
| `https://eds.st.com`、`https://wiki.st.com/stm32mcu/…`、`https://www.st.com/bin/st/getAd.json` | 帮助与广告 |
| `https://www.google-analytics.com/collect` | 遥测（受 `user_analytics` 与隐私声明控制） |
| `HKLM App Paths\STM32CubeProgrammer.exe` | 本机 CubeProgrammer 定位（安全启动烧写） |

`swmgr connection status` 走 HTTP 探测；`proxy type` 支持
`NO_PROXY/SYSTEM_PROXY/USER_PROXY`；`swmgr hello` 会先查代理状态（离线环境需注意）。

---

## 9. 测试/内部工具面（同样保留）

`xts`（compliance test suite）、`xtest`、`xbuild`、`xcopy`（9 参数）、
`ocxtest`、`tooltip log on/off`（把 GUI tooltip 文本落日志）、`popupwrapper`
（`record_answer/clear/set`，用于无人值守弹窗）、`updateIpUI <ip>`、
`isPluginError <plugin>`、`simulate cubeIDE <bool>`、`user_analytics <bool>`、
`import hackmxdb`（数据库热补丁模式）、`check mcus xml/modes`（全库体检）、
`get codegeneratormode`、`bootpath wizard`。
这些在 MCP 里分别由 `compliance`、`ide_bridge`、`porting`、`cli` 覆盖。

---

## 9.5 RTOS / 中间件（实测定论）

这一块靠运行时取证才定下来，是"看起来能用其实丢数据"的典型：

| 事实 | 证据 |
|---|---|
| 中间件 IP 的"启用"不是 `Mcu.*.Mode`，而是把名字写进 `Mcu.IP0..N`（`Mcu.IP3=FREERTOS`） | 板卡 `.ioc` 与运行时 `config saveext` 对照 |
| `set mode FREERTOS CMSIS_V2` **确实生效**（日志 `Current active RTOS is FREERTOS [Cortex-M3NS]`），但整张 RTOS 表只出现在 **扩展保存** `project_ext.ioc` 里（`FREERTOS.Tasks01=…`、`FREERTOS.config*.Ext=…`、`FREERTOS.Mutexes01.Ext=` 等 60+ 键） | `build/mw2/project_ext.ioc` |
| `project.ioc`（普通 `config saveas`）**不含**这些默认值，所以只读主文件会误判"RTOS 没启用" | 同上与 `analysis/ioc_grammar.json` 的 `FREERTOS.*` 统计 |
| 对象格式：`<PREFIX>.<列表名><两位序号>=字段1,字段2,…`，字段顺序由 `rtos_apis.xml` 声明；`IPParameters` 列出键名才持久化 | `FREERTOS.Tasks01=defaultTask,24,128,StartDefaultTask,Default,NULL,Dynamic,NULL,NULL` |
| CMSIS v1 7 类对象 / v2 8 类（tasks, queues, timers, binarySems, countingSems, mutexes, recursiveMutexes, events），字段 35/40 个 | `analysis/rtos_model.json` |
| 字段可用性由 **JavaScript** 判定（`allocationType === 'Static'`），由 GraalJS + `RtosBindings` 求值 | `docs/rtos_apis.xml` 的 `<enabled condition>` |
| 自定义中间件用 `add mw <name> <root_dir> <mode_file> <config_file> <template_dir>`（5 参数）注册 | `add`（裸）回显的用法串 |
| 生效顺序：改 `.ioc` → `config load` → `config saveext`；CubeMX 自己重算派生表 | `rtos_object_write` 的实现与测试 |

对应工具：`rtos_schema` / `rtos_status` / `rtos_objects` / `rtos_object_write` /
`rtos_config`（写后强制经引擎 reload+save，保证 .ioc 是权威）。

## 10. 遗留不确定项（诚实标注）

1. `MMT *` 在无内存映射特性的 MCU（F1）上返回 KO 并回显全局用法；在 H7RS/U5/N6
   上的完整区域语义需要相应固件包与工程（本机仓库未安装完整包）才能观测。
2. `get sub-modes <IP>` 会把正文与终止符粘在同一行，且正文重复两次
   （`No DebugSysTickNo DebugSysTick0 OK`）；引擎已按"尾部终止符"成帧，但
   尾部数字可能与正文混在一起，`submode_state` 的返回值需按文本处理。
3. React 客户端的完整模块图未做（单文件 `main.d8df2386.js` 令 REA 的 JS worker
   超出 1 024 MiB 堆；已用字面量扫描取到桥接口与端点集合）。
4. `third_parties_plugins/com.st.stm32cube.ide.common.services.mx.jar-1.19.0-b1.jar`
   （62 MB，仅 30 个条目：本体是嵌套打包的 services 汇总）未逐类展开。
5. `import hackmxdb`、`bootpath wizard` 会改变 DB 或打开向导，只登记用法、未实跑。
