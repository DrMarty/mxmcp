# 变更日志

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号用 [语义化版本](https://semver.org/lang/zh-CN/)。

## [1.1.0] — 2026-10-29

### 新增：独立模式（不需要 CubeMX 安装）

* **数据包**（`python -m mxmcp.bundle build`）：9.1 MB，2 019 颗 MCU /
  245 083 引脚（含可复用信号与 GPIO IOModes）/ 138 565 个 IP 条目 / 274 套 IP 模式 /
  215 板卡 / 1 756 个模板清单 / 192 个 IP 的 HAL Init 参数树。
* **独立引擎**（`standalone.py`）：在内存里维护与 `.ioc` 同构的工程，真实校验
  引脚-信号合法性、信号唯一性、IP 存在性、模式合法性；`IPParameters` 自动登记。
* **独立代码生成**（`codegen.py`）：从 HAL Init 参数树生成 `main.c/main.h/`MSP`/
  IRQ/`Makefile` 骨架，参数值直接来自 `.ioc`。
* 无安装时引擎工具**立刻**返回可操作错误，不再等待 JVM 超时。
* 新增 12 个工具：`standalone_info/create/open/pin/signals/mode/param/nvic/view/
  validate/generate/mcu`。

### 新增：逆向覆盖面补齐

* 内嵌归档**全量重建**：54 774 条目（此前只拿到 12 666），0 失败；
  `com/st/components/**`（含 `CommandLineManager`）首次被静态反编译。
* CLI 注册表从 89 条扩到 **267 条**（64 个命令头），逐条记录注册类、arity、help。
* 插件协议：**217 个 opcode + 30 个返回码**（`analysis/plugin_protocol.json`）。
* 数据面：`db_schema`（6 690 个 XML 的元素/属性/值域）、条件表达式语言
  （**636 975** 条，含 `$IpInstance`/`Semaphore_*`/`MOD()`/`IF()`）、
  `.ioc` 语法（506 份语料，**7 670** 键模式）、模板模型（**2 706** 个变量键）、
  CubeIDE-MX 28 个服务（mxScratch 交换格式）。
* 运行时：`dma`/`mdma`/`gic`/`NVIC`(15 动词)/`MMT`/`import`/`selector` 的实测语义；
  发现 `dma`/`NVIC` 等把结果写在 log4j 行、且存在终止符粘行，已在 `engine.py` 处理。
* RTOS：`rtos_apis.xml`（CMSIS v1 7 类 / v2 8 类，75 个字段）+ 对象存储格式
  `<PREFIX>.<List><nn>=v1,v2,…`，并实现 5 个 `rtos_*` 工具。
* 中间件：`MiddleWareConstants` 的 36 个实例名 + 模板钩子，`middleware_list/add`。
* 信任链与网络：Authenticode（ST 签名/DigiCert 时间戳/证书有效期）、
  updater 站点与 md5 校验、`PacksControlFlags` 拒绝名单、CAS/OAuth 登录端点。
* 其他：`utilities`（STM32PackCreator 4 823 类）、`Uninstaller`（IzPack）、
  `olddb`（DB.6.0.141.tar.bz2）、`third_parties_plugins`（20 个 p2 bundle）。

### 新增：开源工程化

* `LICENSE`（MIT + THIRD-PARTY NOTICES：ST 派生数据不随仓库分发）。
* `pyproject.toml`（零运行时依赖，`mxmcp` / `mxmcp-bundle` 两个入口）。
* GitHub Actions：lint + 协议自检 + 单元测试（Ubuntu/Windows × py3.9/3.11/3.12）
  + 合规检查 + wheel 检查。
* `tools/check_compliance.py`：CI 阻止提交任何 ST 派生产物。
* 文档：`ARCHITECTURE.md`、`DATA_MODEL.md`、`FEATURES.md`（功能覆盖矩阵）、
  `STANDALONE.md`、`SECURITY_NETWORK.md`、`CLI_REGISTRY.md`。

### 修复

* `engine.py`：终止符粘行（`...0 OK`）、log4j 应答、提示符粘连三种成帧。
* `mode_set`：中间件 IP 需要不带引号的形式，现在两种都试并在结果里回传 log。
* `mode_list`：中间件 IP 的 `get modes` 返回 KO 时回退到 db 模式表。
* `rtos_*`：从 `project_ext.ioc` 合并默认值（CubeMX 只在扩展保存里写 RTOS 表）。
* `store.get`：`project_id` 省略时回退到最近使用的工程。

## [1.0.0] — 2026-10-28

首个可用版本：72 个工具，覆盖工程生命周期、选型、引脚、时钟、外设参数、
代码生成、软件包、`.ioc` 读写与 CLI 兜底；含端到端与单元测试。
