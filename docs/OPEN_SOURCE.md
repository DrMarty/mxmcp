# 开源说明：仓库结构、发布流程与合规边界

## 1. 这个仓库是什么 / 不是什么

**是**：一个独立实现的 MCP 服务器（`mxmcp`），它
① 通过 STM32CubeMX 的**官方命令行**驱动本机安装（hybrid 模式），或
② 用自带数据包完全离线工作（standalone 模式）。

**不是**：CubeMX 的重打包、破解版、或任何 ST 内容的再分发。仓库里没有
ST 的二进制、固件包、模板或数据库文件——这些由**使用者用自己合法安装的
CubeMX**在本地生成（`python -m mxmcp.bundle build`）。

## 2. 仓库结构

```
mxmcp/                  源码（MIT）
├── mxmcp/
│   ├── rpc.py          MCP / JSON-RPC 2.0
│   ├── server.py       入口（--selftest / --list-tools / --call）
│   ├── engine.py       CubeMX 会话引擎（成帧、超时、挂起恢复）
│   ├── store.py        工程池、保存/重载、料号解析
│   ├── ioc.py          .ioc 读写（含 ext 合并视图）
│   ├── catalog.py      安装目录索引（无安装时走数据包）
│   ├── bundle.py       数据包 build/info/verify + Pack 读取
│   ├── standalone.py   独立引擎（真实校验）
│   ├── ipmodes.py      IP 模式/参数 schema
│   ├── codegen.py      独立 C 代码生成
│   ├── firmware.py     固件包完整性扫描
│   └── tools_*.py      113 个 MCP 工具
├── tests/              6 个测试脚本（unit/e2e/advanced/rtos/middleware/standalone）
├── tools/              可复现取证脚本 + 合规检查
├── docs/               逆向与使用文档
├── LICENSE             MIT + THIRD-PARTY NOTICES
├── CONTRIBUTING.md
├── CHANGELOG.md
└── pyproject.toml      零运行时依赖
```

被 `.gitignore` 排除（**本地生成，不发布**）：

```
mxmcp/data/cubemx-db.zip            数据包（9.1 MB）
mxmcp/data/{ip_modes,config_slim,middleware,rtos_model,cli_registry,...}.json
analysis/                           逆向产物（api_index、db_schema、ioc_grammar…）
_extract/  cls/  probe/  build/     提取与调试目录
docs/javap/  docs/rtos_apis.xml     反编译与内嵌资源副本
```

## 3. 发布流程

```bash
# 1) 校验源码
ruff check .
python -m mxmcp.server --selftest
pytest tests -q

# 2) 合规检查（必须通过）
python tools/check_compliance.py

# 3) 构建发行物
python -m build          # dist/mxmcp-<ver>.tar.gz + .whl（不含任何 ST 数据）

# 4) 打 tag
git tag v1.1.0 && git push --tags
```

CI（`.github/workflows/ci.yml`）在 Ubuntu/Windows × py3.9/3.11/3.12 上跑
lint、协议自检、单元测试、合规检查，并断言 wheel 里没有任何 ST 派生文件。

## 4. 使用者必读：装机后先建数据包

standalone 模式需要数据包：

```bash
python -m mxmcp.bundle build --cubemx-root "/path/to/STM32CubeMX"
python -m mxmcp.bundle verify
python -m mxmcp.server --selftest
```

没装 CubeMX 时就只能使用**纯代码路径**（协议、工具签名、`.ioc` 读写、
工程模型），选型/引脚/生成会给出明确提示。这是刻意的设计：数据必须由
使用者从自己的安装件生成。

## 5. 逆向边界（我们做了什么、没做什么）

做过的（全部在本地、针对自己的安装件）：

* 静态：内嵌归档结构分析、`javap` 类/方法/字段清单、常量池字符串与端点扫描、
  XSD/XML 数据模型、`.ioc` 与模板语料统计、PE 证书/导入表/资源表。
* 动态：`-i`/`-q` 交互协议、267 条命令的实测语义、hang 场景归类。
* 产物：数据包与 `analysis/*.json`，供本机互操作与文档使用。

没做、也不提供：

* 绕过/破解任何许可或登录校验（`login`/`swmgr` 只是调用官方命令）。
* 分发 ST 的二进制、固件包、模板或数据库。
* 修改 CubeMX 安装或注册表。

## 6. 商标

STM32、STM32CubeMX、STM32Cube 是 STMicroelectronics International N.V. 的商标。
本项目与 ST 无隶属关系，也未获其背书；名称仅用于说明兼容对象。
