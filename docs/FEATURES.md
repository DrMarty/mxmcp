# 功能覆盖矩阵 —— CubeMX 的全部能力 → CLI → MCP 工具

这张表是"完整逆向所有功能"的验收清单：每一行都是 CubeMX 里真实存在的功能，
都能在 MCP 里找到入口。依据是 `analysis/cli_registry.json`（267 条注册）、
`analysis/cli_usage_tables.txt`（运行时用法表）、`analysis/api_index.json`
（3 222 类 / 41 841 方法）与 `analysis/plugin_protocol.json`（217 opcode）。

列含义：
- **CLI**：驱动它的官方命令（`cli` 工具可原样执行任意一条）
- **MCP**：封装好的工具（若是"—"则只能用 `cli` 兜底）
- **离线**：✅ = 不装 CubeMX 也能用（走自带数据包 / 独立引擎）；❌ = 需要官方引擎

---

## 1. 启动页 / 选型

| 功能 | CLI | MCP | 离线 |
|---|---|---|---|
| 按家族/型号搜索 | —（GUI 选择器） | `mcu_search` `family_list` `family_mcus` `mcu_info` | ✅ |
| 引脚功能反查 | `get functions <pin>` | `mcu_pin_functions` `pin_functions` | ✅ |
| 板卡列表/搜索 | `loadboard` | `board_list` `board_search` `project_load_board` | ✅ |
| 参数化选型（商业库） | — | `product_db`（只读 SQLite，19 张表 / 17k CPN） | ✅ |
| 交叉选择/替代料 | — | `product_db` + `catalog_index` | ✅ |
| 选型器表格驱动 | `selector list mcus` `selector set peripheral` | `selectors` | ❌（需 GUI 对话框） |
| 示例工程选择 | `exampleselector list examples` … | `selectors` | ❌ |

## 2. Pinout & Configuration

| 功能 | CLI | MCP | 离线 |
|---|---|---|---|
| 引脚清单/当前映射 | `get pinout` | `pinout_get` | ✅ |
| 绑定/复位/清空/锁定/保留 | `set pin` `reset pin` `clearpinout` `lock pin` `set pinreservation` | `pin_set` `pin_reset` `pin_clear_all` `pin_lock` `pin_reserve` | ✅（`standalone_pin`） |
| 单引脚可选信号 | `get functions` | `pin_functions` `standalone_signals` | ✅ |
| 外设列表 | `get mcu peripherals` | `peripheral_list` `mcu_info` | ✅ |
| 模式列表（全量/可用/已映射） | `get modes` `get available modes` `get mapped modes` | `mode_list` `mode_catalog` | ✅（`mode_catalog` 走 db） |
| 启用/关闭/检查模式 | `set mode` `reset mode` `check mode enabled` | `mode_set` `mode_reset` `mode_check` `standalone_mode` | ✅ |
| 子模式树 | `get sub-modes` `get sub-mode-state` | `sub_modes` `submode_state` | ❌ |
| 参数读写/批量/刷新 | `get/set ip parameters` `IPParameters` | `ip_param_get` `ip_param_set` `ip_params_set` `ip_params_dump` | ✅（`standalone_param`） |
| 取值域与限制 | `get mode_param_possvalue` `get mode_param_pattern` | `clock_param_possible_values` `mode_pattern` `value_check` | ✅（`value_check` 需引擎） |
| GPIO 参数（标签/上下拉/速度） | `set gpio parameters` | `gpio_params` `gpio_set` | ✅ |
| NVIC（15 个动词） | `NVIC enable/disable/get_*/set_*` | `nvic_read` `nvic_write` `standalone_nvic` | ✅（独立引擎存 NVIC.<IRQ>） |
| DMA 请求/流/参数 | `dma list_all/list/available_*/is_available/add/delete/set_flow/set_param` | `dma_query` `dma_mutate` | ❌ |
| MDMA 通道/请求 | `mdma list_*/add_*/delete_*` | `mdma_query` `mdma_mutate` | ❌ |
| GIC（MP1/MP2 中断控制器） | `gic get_*/enable/disable/set_triggering_mode` | `gic_query` `gic_mutate` | ❌ |
| 中间件集成 | `set mode <MW> <mode>` `add mw` | `middleware_list` `middleware_add` | 部分（列表 ✅） |
| RTOS 对象（任务/队列/信号量…） | — （GUI 数据编辑器） | `rtos_schema` `rtos_status` `rtos_objects` `rtos_object_write` `rtos_config` | ✅（写 .ioc + 引擎重载） |
| 时钟树 | `clock resolution` | `clock_get` `clock_set` `clock_resolve` | ❌（求解需引擎） |
| 功耗计算 | —（power 插件 225 个模型） | —（数据已提取，见 `analysis/subsystem_contracts.json`） | ✅ |
| 约束导入 | `import GPIOconstraint` `import channelconstraint` | `porting` | ❌ |

## 3. Project Manager

| 功能 | CLI | MCP | 离线 |
|---|---|---|---|
| 新建/打开/保存/另存/删除 | `load` `config load/saveas/saveext` | `project_create` `project_open` `project_save` `project_save_as` `project_delete` `standalone_create` `standalone_open` | ✅（独立） |
| 加载 MCU / 板卡 | `load` `loadboard` `tinyload` | `project_load_mcu` `project_load_board` | ✅（建工程）/❌（loadboard） |
| 工程选项（工具链/堆栈/文件布局） | `project toolchain/compiler/path/name/…` | `project_options` `project_set_option` | ✅（存 .ioc） |
| 代码生成 | `project generate` `generate code` | `project_generate` `generate_code` `standalone_generate` | ✅（`standalone_generate`） |
| 生成内容检查 | — | `project_files` `verify` `standalone_validate` | ✅ |
| 报告 / CSV / 脚本导出 | `csv pinout` `export script` | `project_report` `project_csv` `project_export_script` | ✅ |
| 两工程比较 | `cpload project1/2` `cpexport` | `ioc_compare` `project_diff` | ✅（`project_diff`） |
| 导入配置（移植到另一颗 MCU） | `import openioc/config/try auto import/add_compatibility_rule` | `porting` | ❌ |
| 工具链联动 | `simulate cubeIDE` | `ide_bridge` | ❌ |

## 4. Tools

| 功能 | CLI | MCP | 离线 |
|---|---|---|---|
| 内存映射（MMT，H5/H7RS/N6） | `MMT dump/reserved/resetReserved/load-save pre-config/ThreadX` | `mmt` | ❌ |
| LPBAM 多上下文 | `MultiConfig get/add/delete/rename/select LPBAMConfiguration` | `lpbam` | ❌ |
| 数据库刷新 | `swmgr refresh/install/remove/set repository` | `swmgr` | ❌ |
| 产品数据库查询 | — | `product_db` | ✅ |
| 版权/许可文件 | — | `analysis/strings_report.json`、`docs/SECURITY_NETWORK.md` | ✅ |

## 5. 软件包 / 库管理

| 功能 | CLI | MCP | 离线 |
|---|---|---|---|
| 固件包状态 | `swmgr` `get <IP> …` | `firmware_packages`（本地仓库扫描 + 完整性判据） | ✅（扫描） |
| CMSIS-Pack 组件 | `pack status/enable/disable/validate/context/migrate` | `pack_status` `pack_enable` `pack_disable` `pack_validate` | ❌ |
| X-CUBE 下载 | `xcubedl` | `xcubedl` | ❌ |
| 登录/登出 | `login` `logout` `login_with_gui` | `login` `logout` | ❌ |
| 模板库 | — | `template_list` `ip_library` | ✅ |

## 6. `.ioc` 与协议层

| 功能 | CLI | MCP | 离线 |
|---|---|---|---|
| 任意键读写/删除 | — | `ioc_get` `ioc_set` `ioc_delete` `ioc_import` `ioc_export` | ✅ |
| 完整状态视图 | `get pinout` + 读文件 | `standalone_view` | ✅ |
| 命令注册表 | `help` | `command_catalog`（267 条，含注册类/arity/help） | ✅ |
| 任意 CLI 执行 | — | `cli` `cli_batch` `cli_help` | ❌ |
| 引擎运行时属性/日志级别 | `getprop` `setprop` `getenv` `log` | `runtime_props` | ❌ |
| 一致性检查 | `check mcu modes` `xts` `xtest` `pinout check keep user placement` | `compliance` | ❌ |

## 7. 独立（无安装）能力

`standalone_*` 系列 + 所有 ✅ 工具都只依赖 `mxmcp/data/cubemx-db.zip`
（9.1 MB：2 019 颗 MCU / 245 083 引脚 / 138 565 IP 条目 / 274 套 IP 模式 /
215 板卡 / 1 756 模板清单 / HAL Init 参数树）。
详见 [STANDALONE.md](STANDALONE.md)。

---

## 8. 明确无法在无安装环境复现的部分（诚实边界）

| 能力 | 原因 | 替代 |
|---|---|---|
| 时钟树求解 | 求解器是 `clock.jar` 里的专有算法（4 种进入路径 + 约束传播） | 手工给 `RCC.*` 参数，或装 CubeMX 用 `clock_set` |
| ST 原版代码生成 | 1 756 个 FreeMarker 模板 + 每 IP 的产品逻辑 | `standalone_generate` 产出可编译骨架，字段来自 .ioc |
| 固件包下载/安装 | 需要 my.st.com 登录 + 官方 updater 协议 | `firmware_packages` 扫描本地，或用 `swmgr` |
| Pack 组件启用 | 依赖 `TP_ADVANCED_MODE` 与官方 pack 索引 | `product_db` + `middleware_list` 提供等价信息 |
| GUI 选择器/向导 | 命令只在对话框实例化后注册 | 离线 catalog 工具覆盖同一数据 |
| 功耗/LPBAM/DDR 计算 | 计算在插件 jar 内，数据可提取但算法未重写 | 数据见 `analysis/subsystem_contracts.json` |
