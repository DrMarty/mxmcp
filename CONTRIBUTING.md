# 贡献指南

感谢参与。这个项目的目标是：**用 MCP 把 STM32CubeMX 的工程能力完整开放出来，
并且在没有 CubeMX 的机器上也能用**。

## 1. 环境

```bash
python -m venv .venv && . .venv/Scripts/activate     # Windows: .venv\Scripts\activate
python -m pip install -e ".[dev]"
```

仓库里**不含**任何 ST 派生数据（见 [LICENSE](../LICENSE) 的 THIRD-PARTY NOTICES）。
要在本地跑完整功能：

```bash
# 有 CubeMX（hybrid 模式）
set MXMCP_CUBEMX_ROOT=C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX

# 只有代码（standalone 模式）：先生成数据包
python -m mxmcp.bundle build --cubemx-root "C:\Program Files\...\STM32CubeMX"
python -m mxmcp.bundle verify
```

`mxmcp/data/*.zip`、`analysis/`、`docs/javap/` 都被 `.gitignore` 忽略，
`tools/check_compliance.py` 会在 CI 里强制这一点。

## 2. 代码结构

```
mxmcp/
├── rpc.py            MCP/JSON-RPC 2.0（换行分隔；也接受 Content-Length 帧）
├── server.py         入口：--selftest --list-tools --call
├── engine.py         CubeMX 会话（-i 常驻；成帧/超时/挂起恢复）
├── store.py          工程池、保存/重载、料号解析
├── ioc.py            .ioc 读写（含与 project_ext.ioc 的合并视图）
├── catalog.py        安装目录 db 索引；无安装时自动走数据包
├── bundle.py         数据包 build/info/verify + Pack 读取
├── standalone.py     独立引擎（引脚/模式/参数/NVIC，真实校验）
├── ipmodes.py        IP 模式与参数 schema
├── codegen.py        独立 C 代码生成（HAL Init 参数树驱动）
├── firmware.py       固件包完整性扫描
└── tools_*.py        113 个 MCP 工具，按族拆分
```

## 3. 改动的硬性要求

1. **不要绕过引擎的成帧规则**。CubeMX 的应答有三种形态：独立终止符行、
   终止符粘在正文尾部、以及走 log4j 行；`engine.py` 全部处理了，改动请保留。
2. **参数必须登记**。写 `<IP>.<param>` 时同时写入 `<IP>.IPParameters`，否则
   CubeMX 重新加载会丢弃它（`standalone.py` 与工具层都遵守）。
3. **引脚名用完整名**（`PC13-TAMPER-RTC`），工具层负责从短名解析。
4. **不要对未知 MCU 直接 `load <料号>`**：会让解释器永久挂起，必须先解析成
   db RefName（`Catalog.resolve_mcu`）。
5. **离线优先**。任何只依赖数据的能力，都要能在没有安装时工作
   （`catalog`/`bundle`/`standalone`/`ipmodes`/`codegen` 的分支就是范例）。
6. **不要提交 ST 派生文件**。CI 会拒绝。

## 4. 测试

```bash
pytest tests -q                  # 单元测试（无需 CubeMX）
python tests/test_standalone.py  # 把安装路径指向不存在的目录，验证独立模式
python tests/test_e2e.py         # 需要 CubeMX（hybrid）
python tests/test_advanced.py    # 新增的 dma/nvic/gic/mmt/porting 等
python tests/test_rtos.py        # RTOS 对象读写
python tests/test_middleware.py  # 中间件集成
```

PR 要求：`ruff check .` 干净、相关测试通过、README/docs 同步更新。

## 5. 逆向证据

`tools/` 下的脚本是可复现的取证工具（javap 扫描、数据包构建、CLI 探针等）。
提交与逆向相关的改动时，请说明结论来自哪份 `analysis/*.json` 或哪次实测输出，
不要凭印象写文档——docs 里每张表都应能追溯到脚本产物。

## 6. 许可

提交即表示你同意以 MIT 许可发布你的贡献（见 LICENSE）。涉及 ST 内容的部分
（数据包、反编译产物）不属于贡献范围。
