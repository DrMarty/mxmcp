# STM32CubeMX CLI 参考（实测 + 反编译，v6.15.0）

本文件是 `mxmcp` 的行为依据：所有条目都在本机 CubeMX 6.15.0 上跑通或反编译确认。
`cli` / `cli_batch` 工具可以执行下面任意一条命令，其余工具都是这些命令的类型化封装。

启动方式（官方，UM1718 亦有记载）：

```bat
rem 交互式
jre\bin\java -jar STM32CubeMX.exe -i
rem 脚本 + 无 UI（MCP 会话引擎使用这一种做冷启动/批处理）
jre\bin\java -jar STM32CubeMX.exe -q script.txt
rem 脚本 + UI
jre\bin\java -jar STM32CubeMX.exe -s script.txt
```

## 1. 交互协议（`-i`）

* 提示符 `MX> ` **不带换行**；命令回显后输出结果，最后一行是 `<n> OK` 或 `<n> KO`。
* `n` 是引擎内部计数，不可依赖具体数值。
* 打印为空的操作（`set pin`、`set mode`、`config saveas`）之后提示符独占一行；
  下一条命令的应答可能被拼到同一物理行（`MX> PC13: GPIO_Output`），需要剥掉 `MX>` 前缀。
* 部分列表型应答会被引擎自身重复打印（`USART1: Asynchronous, USART1: Asynchronous,`、
  `GPIO_OutputPC13-TAMPER-RTC: GPIO_Output`），解析器会去重。
* **重要**：命令若因弹窗/下载而无法返回，解释器会卡死，后续命令全部超时。
  `mxmcp` 的会话引擎用超时杀掉进程并在下次调用时重新 `config load` 恢复。

## 2. 命令总表（89 条注册项，来自 plugins/** 的 `addCommand` 常量池）

| 族 | 子命令与语义 |
|---|---|
| `load <mcu>` | 新建工程。**只接受 db RefName**（`STM32F103C(8-B)Tx`），传裸料号 `STM32F103C8T6` 会让解释器永久挂起。 |
| `tinyload <mcu>` | 只加载引脚图，不建工程。 |
| `loadboard <board> <allmodes\|nomode>` | 板卡工程；`nomode` 只带默认引脚，`allmodes` 带全部外设默认模式。 |
| `config load/save/saveas/saveext <file>` | 读/写 .ioc。`save` 在未初始化路径时挂起，MCP 只用 `saveas`/`saveext`。 |
| `import config <file>` / `import openioc` | 把另一个 .ioc 合并进当前工程。 |
| `get pinout` | `pin: signal` 全表。 |
| `get functions <pin>` | 该引脚可选的信号名。可传完整名 `PC13-TAMPER-RTC`。 |
| `get signal <pin>[/regex]` | 单引脚当前信号。 |
| `set pin <pin> <signal>` | 绑定信号；短名 `PC13` 与完整名都接受。 |
| `reset pin <pin>` / `reset pin-signal` / `reset signal <signal>` | 解绑。 |
| `clearpinout` | 清空全部引脚。 |
| `lock pin <pin> <true\|false>` | 锁定/解锁引脚。 |
| `set pinreservation <pin>` | 预留引脚。 |
| `get modes/available modes/all/mapped modes <regex>` | 外设模式（全部/可用/已设置）。 |
| `get mode active/available/all <periph>` | 单外设模式详情。 |
| `set mode <periph> "<mode>"` | 启用模式；**模式名必须带引号**。 |
| `reset mode <periph> "<mode>"` | 关闭模式。 |
| `check mode enabled <periph> "<mode>"` | 是否已启用。 |
| `check mcu modes` | 当前 MCU 不可用模式清单。 |
| `check mcus xml` / `check mcus modes` | 全库自检（很慢）。 |
| `get sub-modes <periph>` / `get sub-mode-state <periph> <path>` | 复合模式状态。 |
| `get mcu name/package/peripherals` | MCU 信息。 |
| `get ip parameters <ip> <param>` | 读参数。 |
| `set ip parameters <ip> <param> <value>` | 写参数。 |
| `set ip parameters <ip> IPParameters a,b,c` | **把参数名登记进 `.ioc` 的 `IPParameters`**；不登记则只存内存、不落盘。 |
| `set username <ip> <name>` | 改实例名（影响生成代码前缀）。 |
| `get gpio parameters <pin> <param>` / `set gpio parameters <pin> <param> <value>` | GPIO 参数，**pin 必须是完整名**（`PC13-TAMPER-RTC`）。 |
| `get available-analog-signals <pin>` | 模拟通道。 |
| `get possible remaps <signal regex>` | 重映射引脚。 |
| `NVIC enable/disable/set_priority/set_subpriority/set_prioritygroup ...` | 中断配置（由 `export script` 实录确认）。 |
| `clock resolution` | 时钟树求解/收敛。 |
| `project path/name/toolchain/compiler/toolchainlocation <v>` | 工程目标设置。`project compiler` 只对多编译器工具链有效。 |
| `project couplefilesbyip <0\|1>` | 每 IP 独立文件 / 全部放 main。 |
| `project generateunderroot <0\|1>` | 生成到工程根目录。 |
| `project setCustomFWPath "<dir>"` | 指定固件包目录；写入 .ioc 时**转成以 .ioc 为基准的相对路径**。仅设置它不足以绕过联网检查，`ProjectManager.FirmwarePackage` 的版本还要与仓库目录一致。 |
| `project set/get stacksize, heapsize` | 栈/堆大小。 |
| `project set/get stackbycontext, heapbycontext <ctx>` | 多核按上下文。 |
| `project save` / `project import` | 工程设置存取。 |
| `project generate` | 生成完整工程（代码+驱动+IDE 工程）。固件包缺失时会等待联网/登录 → 无 UI 下挂起。 |
| `generate code <dir>` | 只生成 MX 代码。 |
| `generate all_code_in_main` / `generate one_file_per_ip` | 生成布局。 |
| `SetStructure Advanced\|Basic` | 工程结构。 |
| `SetCopyLibrary "copy all"\|"copy only"\|"copy as reference"` | 库拷贝方式。 |
| `setDriver <periph> HAL\|LL` | 驱动层选择。 |
| `csv pinout <file>` | 引脚 CSV 导出（`purpose,position,name,type,signal,label,...`）。 |
| `export script <file>` | **把当前配置导出成可重放命令脚本**。 |
| `loadboard`, `add mw <name> <root> <mode> <config> <templates>` | 自定义中间件（.mw 工程）。 |
| `pack enable/disable/validate/context/migrate/status` | CMSIS-Pack 组件。 |
| `swmgr refresh/install/remove/set repository/set proxy ...` | Cube 固件包与包管理。 |
| `login <email> <password> <y\|n>` / `logout` / `login_with_gui` | ST 账号。 |
| `xcopy`, `xts`, `xtest`, `xbuild`, `ocxtest`, `xcubedl <pack>` | 示例工程复制/测试/构建/下载。 |
| `MultiConfig selectMXProject/selectLPBAMConfiguration/addLPBAMConfiguration/renameLPBAMConfiguration/deleteLPBAMConfiguration/getLPBAMConfigurations` | 多配置与 LPBAM。 |
| `pinout check/uncheck keep user placement` | 保持用户布局。 |
| `updateIpUI <IpName>`、`tooltip log on/off`、`isPluginError <plugin>`、`log <level>` | 诊断。 |
| `simulate cubeIDE <true\|false>`、`user_analytics <true\|false>` | 环境开关。 |
| `setprop/getprop/getenv` | JVM 属性/环境变量。 |
| `popupwrapper set/unset/record_answer/unrecord_answer` | 弹窗应答注入（脚本化 GUI 弹窗）。 |
| `cpload project1|project2`、`cpexport` | 配置对比（copy/paste 工程）。 |
| `import try import`、`import try import_and_log`、`import try auto`、`import get report` | 跨 MCU 导入报告。 |
| `import hackmxdb`、`import GPIOconstraint`、`import channelconstraint`、`import add_compatibility_rule` | 引脚/通道约束与兼容规则。 |
| `possible_value ip` / `not_a_possible_value ip` | 参数取值校验。 |
| `disable project generate <true\|false>` | 禁用生成按钮。 |
| `exit` / `exit_mx` | 退出。 |

## 3. `.ioc` 格式要点

```
#MicroXplorer Configuration settings - do not modify
Mcu.Name=STM32F103C(8-B)Tx        <- db RefName
Mcu.UserName=STM32F103C8Tx        <- 用户输入料号
Mcu.Pin0=PC13-TAMPER-RTC          <- 引脚全名（不是 PC13）
Mcu.IP0=USART1
PA9.Signal=USART1_TX
PA9.Mode=Asynchronous
PA9.Locked=true
PC13-TAMPER-RTC.GPIOParameters=GPIO_Label
PC13-TAMPER-RTC.GPIO_Label=LED
USART1.IPParameters=VirtualMode   <- 只有列在这里的参数才会保存
RCC.IPParameters=...
RCC.PLLMUL=RCC_PLL_MUL9
RCC.PLLSourceVirtual=RCC_PLLSOURCE_HSE
RCC.HCLKFreq_Value=72000000       <- 求解结果，只读
ProjectManager.TargetToolchain=Makefile
ProjectManager.FirmwarePackage=STM32Cube FW_F1 V1.8.0
ProjectManager.CustomerFirmwarePackage=..\..\..\STM32Cube\Repository\STM32Cube_FW_F1_V1.8.0
```

注意：
* 值里的冒号写成 `\:`（如 `NVIC.SysTick_IRQn=true\:15\:0\:...`）。
* HSE 时钟树生效需要 `PD0-OSC_IN.Signal=RCC_OSC_IN`、`PD1-OSC_OUT.Signal=RCC_OSC_OUT`；
  只设 `PLLSourceVirtual=RCC_PLLSOURCE_HSE` 而不复用引脚，时钟树仍按 HSI 求解（8 MHz）。
* 固化固件版本：`ProjectManager.FirmwarePackage` 必须与实际安装的目录版本一致，
  否则 `project generate` 会尝试联网下载。把版本改成仓库里完整包的实际版本，再配合 `project setCustomFWPath`，可完全避免联网。

## 4. 已验证的生成行为

| 场景 | 结果 |
|---|---|
| CLI 会话内配置 → `project generate`（F1，固件包版本匹配） | OK，约 5 s，913 个文件，含 `Src/main.c`、`Drivers/`、`Makefile` |
| 加载 .ioc → `project generate`，固件版本不匹配 | 一次 KO + `This download action requires prior login`（不挂起）或挂起（无 UI 联网） |
| 首次生成失败（登录提示）后，设置 `project setCustomFWPath <绝对路径>` + 对齐 `FirmwarePackage` 版本 → 重新加载再生成 | OK，234+ 文件，无需登录 |
| 工具链 EWARM / MDK-ARM / STM32CubeIDE / Makefile / CMake | 均能生成；固件包存在时 700–1300 个文件 |

