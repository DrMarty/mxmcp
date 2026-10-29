# 验收记录（最终版）

环境：Windows 10 · Python 3.11 · STM32CubeMX **6.15.0 / DB.6.0.150** · 无第三方运行时依赖
产物：`mxmcp` **113 个 MCP 工具**，双模式（hybrid 驱动官方引擎 / standalone 零安装）

---

## 1. 逆向证据台账

| # | 结论 | 证据产物 | 数量 |
|---|---|---|---|
| 1 | 交付物是 PE32 装载器 + 内嵌 ZIP 的 Java 应用，无需脱壳 | `analysis/cd_entries.json`、`analysis/stub_version.json`、REA PE 结果 | 本地头起 `0x13000`，CD `0xD2F0A03` |
| 2 | 内嵌归档**全量** 54 774 条目可重建（0 失败） | `tools/rebuild_full_jar.py` → `_extract/cubemx_full.jar` | 227 113 372 B |
| 3 | `com/st/components/**` 在归档内（含 `CommandLineManager`） | `docs/javap/`、`analysis/api_index.json` | 196 条目 |
| 4 | 类/方法/字段全量表 | `analysis/api_index.json` | **3 222 类 / 41 841 方法 / 38 255 字段 / 339 包** |
| 5 | CLI 注册表 | `analysis/cli_registry.json`、`docs/CLI_REGISTRY.md` | **267 条 / 64 命令头 / 14 jar** |
| 6 | 运行时用法表（含只读命令回显） | `analysis/cli_usage_tables.txt`、`docs/cli_usage_tables.txt` | 34 个命令族 |
| 7 | 插件 RPC 协议 | `analysis/plugin_protocol.json` | **217 opcode + 30 返回码 + 99 常量** |
| 8 | 数据模型（6 690 个 XML） | `analysis/db_schema.json`、`analysis/db_census.json` | 171 目录 / 2 019 MCU / 1 321 IP Modes / 1 308 Configs |
| 9 | 条件表达式语言 | `analysis/condition_language.json` | **636 975** 条表达式 |
| 10 | `.ioc` 语法 | `analysis/ioc_grammar.json` | 506 份语料 → **7 670** 键模式 |
| 11 | 代码生成模型 | `analysis/template_model.json`、`analysis/config_model.json` | **1 756** 模板 / **2 706** 模型键 / 192 IP 参数树 |
| 12 | IDE 生成后端 | `analysis/cubeide_services.json` | 20 p2 插件 / 28 服务 / mxScratch schema |
| 13 | RTOS 对象模型与存储 | `analysis/rtos_model.json`、`docs/rtos_apis.xml` | v1 7 类 / v2 8 类 / 75 字段 |
| 14 | 中间件名录 | `analysis/middleware_constants.json` | **239 常量 / 36 实例名** |
| 15 | 信任链与端点 | `analysis/strings_report.json`、`docs/SECURITY_NETWORK.md` | 5 证书 / 1560 URL / 460 主机 |
| 16 | 安装树全貌 | `analysis/install_census.json`、`analysis/peripherals_of_install.json` | 11 378 文件 / 1 520 MB / 709 目录 |
| 17 | 其余子系统 | `analysis/subsystem_contracts.json`、`analysis/plugin_resources.json` | power 225 / clock 64 / RIF 70 / PackCreator 4 823 类 |
| 18 | 选型产品库 | `analysis/mcufinder_data_layer.json` | 19 表 / 17 491 CPN / 644 828 属性行 |

## 2. 工具面

```
python -m mxmcp.server --list-tools   ->  113 tools
python -m mxmcp.server --selftest     ->  {"name":"mxmcp","version":"1.1.0"} / tools: 113
```

| 族 | 数量 | 关键工具 |
|---|---|---|
| 工程 | 18 | `project_create/generate/save/diff/report/export_script` |
| 选型（离线） | 15 | `mcu_search/mcu_info/mcu_pin_functions/board_*/mode_catalog/product_db/command_catalog` |
| 引脚外设 | 22 | `pin_set/pin_functions/gpio_*/mode_*/ip_param_*/value_check/submode_state` |
| 中断·DMA·内存 | 10 | `nvic_read/write/dma_*/mdma_*/gic_*/mmt/lpbam` |
| RTOS·中间件 | 7 | `rtos_schema/status/objects/object_write/config/middleware_list/add` |
| 时钟 | 4 | `clock_get/set/resolve/param_possible_values` |
| 生成·校验 | 4 | `project_generate/generate_code/verify/compliance` |
| 移植·比较 | 3 | `porting/ioc_compare/selectors` |
| 软件包 | 8 | `pack_*/swmgr/xcubedl/login/logout` |
| **独立模式** | **12** | `standalone_info/create/open/pin/signals/mode/param/nvic/view/validate/generate/mcu` |
| `.ioc`·兜底 | 10 | `ioc_*/cli/cli_batch/cli_help/runtime_props/ide_bridge` |

## 3. 测试结果

| 脚本 | 需要 CubeMX | 结果 |
|---|---|---|
| `pytest tests/test_smoke.py` | 否 | **12 passed**（协议、`.ioc`、数据包、独立引擎、代码生成、IP 模式、合规声明） |
| `tests/test_standalone.py` | **否** | **通过**：无安装下 建工程→引脚校验→模式→参数→NVIC→生成 6 文件，非法信号被拒，引擎工具立即报错 |
| `tests/test_units.py` | 是 | 通过（含 913 文件真实生成） |
| `tests/test_e2e.py` | 是 | 通过（F1 全流程 / 板卡 / F4 时钟 / CLI 桥） |
| `tests/test_advanced.py` | 是 | **ALL OK**（dma/nvic/gic/mmt/porting/selectors/catalog 全绿） |
| `tests/test_rtos.py` | 是 | 通过（任务/队列/信号量增删改 + 重复名拒绝 + config） |
| `tests/test_middleware.py` | 是 | 通过（FREERTOS 集成 → active IP 报告 → verify） |

静态检查：

```
ruff check mxmcp tests        ->  All checks passed!
python -m mxmcp.bundle verify ->  2028/2028 members ok, mcus: 2019
```

## 4. 独立模式实测（`MXMCP_CUBEMX_ROOT` 指向不存在的目录）

```
tools: 113
mode: standalone | engine: False | pack: True 9107807
counts: {'mcu': 2019, 'pins': 245083, 'ips': 138565, 'families': 27,
         'boards': 215, 'ip_modes': 274}
search: 1 ['STM32F103C(8-B)Tx']
create: STM32F103C(8-B)Tx LQFP48 pins: 44
PA9 signals: ['TIM1_CH2','USART1_TX','GPIO_Input','GPIO_Output','GPIO_ANALOG','GPIO_EVENTOUT']
pin: USART1_TX / USART1_RX / GPIO_Output
invalid pin signal rejected: True
mode/param/nvic: OK
validate ok: True []
generate: 6 files standalone
main.c 含 BaudRate = 115200: True
engine tool without install -> clean error: True
```

## 5. 关键行为（均已固化为代码路径）

1. `load` 只认 db RefName；料号先解析（否则解释器永久挂起）。
2. 参数必须登记进 `<IP>.IPParameters` 才落盘。
3. `config save` 无路径会挂起 → 只用 `saveas`/`saveext`。
4. 应答三种成帧：独立终止符行 / 终止符粘行（`…0 OK`）/ log4j 行（dma、nvic、
   `get mode_param_pattern`）——`engine.py` 全部处理。
5. 引擎超时即杀进程，下次调用自动 `config load` 恢复；结果里 `hung: true`。
6. 固件包版本不一致会触发联网下载（无 UI 会挂起）→ 生成前预检 + 自动固定版本。
7. RTOS 表只在 `project_ext.ioc` 出现 → 读取时合并视图，写入后经引擎 reload 规范化。
8. 中间件 IP 需要不带引号的 `set mode`，且 `get modes` 返回 KO → 回退到 db 模式表。
9. 无安装时引擎工具**立即**返回可操作错误，并指引 `standalone_*`。

## 6. 已知边界（不假装做到的事）

| 项 | 原因 | 现状 |
|---|---|---|
| 时钟树求解 | `clock.jar` 专有算法 | 仅 hybrid；standalone 原样保留 `RCC.*` 参数 |
| ST 原版代码 | 1 756 个 FreeMarker + 产品逻辑 | standalone 生成可编译骨架（`fidelity: standalone`） |
| GUI 选择器/向导 | 命令仅在对话框实例化后注册 | 用离线 catalog 覆盖同一数据 |
| 功耗/LPBAM/DDR 计算 | 插件内算法 | 数据已提取，算法未重写 |
| React 客户端模块图 | 单文件 bundle 超 REA worker 堆 | 已取桥接口与端点；记录为未展开 |
| `pack enable` | 需 `TP_ADVANCED_MODE` + 已下载的第三方包 | 保留为显式工具，报错忠实返回 |

## 7. 复现

```bat
python -m mxmcp.bundle build && python -m mxmcp.bundle verify
python -m mxmcp.server --selftest
python -m pytest tests\test_smoke.py -q
python tests\test_standalone.py            :: 无安装验证
python tests\test_e2e.py                   :: 需 CubeMX
python tools\check_compliance.py           :: 提交前合规检查
```
