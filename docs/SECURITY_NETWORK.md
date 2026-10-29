# 信任链、许可与网络面（取证）

所有条目都来自安装件字节、`javap` 反编译或 `analysis/strings_report.json`
（对 54 774 个条目的常量池与资源扫描）。**未做任何签名验证或链校验**——
这里记录的是产品"声明了什么"，不是"是否正确"。

---

## 1. 交付物身份

| 项 | 值 |
|---|---|
| `STM32CubeMX.exe` SHA-256 | `67b12576eed1c9544668b529458d87e6a9db600cf53492da1534afa8cf1ca0b8` |
| 大小 / 类型 | 227 197 688 B，**PE32 (i386)**，无 TLS/LOAD_CONFIG 目录 |
| imphash | `6011984d7c1f1b97a34d7517a498bff8` |
| 版本资源 | ProductName `STM32CubeMX`，FileDescription `MicroXplorer for STM32Cube`，FileVersion/ProductVersion **`6.15.0-RC4`**，LegalCopyright `STMicroelectronics`；装载器自身版本 `0.1.0.4`（Launch4j） |
| 签名块 | 文件尾 `WIN_CERTIFICATE` @227 187 288，长度 10 400，`certificate_type=2 (pkcs7)`，载荷 SHA-256 `2fe76035…3d784` |
| 签名者 | `STMicroelectronics International N.V.`（CH / Genève，私法组织，注册号 54298350），序列 `0b12c8b575d0d6e16489812ce64cd7c5`，有效期 2022-10-26 → **2025-10-25** |
| 发布 CA | `DigiCert Trusted G4 Code Signing RSA4096 SHA384 2021 CA1`（sha256WithRSA） |
| 时间戳 | `DigiCert Timestamp 2024`，由 `DigiCert Trusted G4 RSA4096 SHA256 TimeStamping CA` 签发 |
| 链内证书 | 5 张（含 `DigiCert Trusted Root G4`、`DigiCert Assured ID Root CA`） |

> 结论：签名是 Authenticode 双层（签名 + 时间戳）。**摘要覆盖范围与链可信度未验证**，
> 且签名证书已到期（时间戳仍可使历史签名有效）。

## 2. 装载器行为（88 个导入函数）

```
ADVAPI32  RegOpenKeyExA / RegQueryValueExA / RegEnumKeyExA / RegCloseKey   → 在注册表里找 JRE
KERNEL32  CreateProcessA / WaitForSingleObject / GetExitCodeProcess        → 拉起 java -jar
          FindResourceExA / LoadResource / LockResource                    → 读取内嵌资源
          CreateMutexA                                                     → 单实例
          GlobalMemoryStatusEx                                             → 计算 -Xmx
          SetEnvironmentVariableA / GetEnvironmentVariableA                → 注入环境变量
          SetUnhandledExceptionFilter / FormatMessageA                     → 错误框
USER32    CreateWindowExA / LoadImageA / SetTimer / ShowWindow / MessageBoxA → 启动 splash
SHELL32   ShellExecuteA                                                    → 打开 URL/文件
msvcrt    _findfirst/_findnext/_open/_read/_chdir/fopen/fwrite             → 解包与日志
```

也就是说：**EXE 自己就是 jar**（本地头起始 `0x13000`，中央目录 `0xD2F0A03`，54 774 条目），
`java -jar STM32CubeMX.exe` 与双击行为等价，UM1718 亦如此记载。

## 3. 完整性与"许可"相关机制

| 机制 | 证据 | 说明 |
|---|---|---|
| 数据库完整性 | `com.st.microxplorer.db.DataBaseIntegrity`、`ThirdPartyIntegrityChecker`、`IntegrityCheckThread`（app jar） | 启动时对 DB/第三方目录做校验；`import hackmxdb` 是官方留给厂商的"热改 DB"开关，会把校验状态置为可改 |
| Pack 校验 | `ThirdPartyCheckIntegrity`、`ThirdPartyCheckPdscCondition` 等 opcode（`analysis/plugin_protocol.json`）；`PdscPackages.checkPdscSchema(...)` + `PackXsdList`（XSD 1.4.0…1.6.3） | 下载后的 `.pack` 走 MD5 + pdsc schema 校验 |
| 包黑白名单 | `db/plugins/updater/PacksControlFlags.xml`（65 KB，`<Flag name="Denied">`，例如全部 Keil DFP） | GUI/CLI 会据此拒绝启用某些包 |
| 下载校验 | `STMUpdaterDefinitions.xml` 的 `ReleaseMD5/ReleaseSize`、`https://sw-center.st.com/packs/cube-finder-db/md5.xml` | 尺寸 + MD5；失败映射到 `Updater_ReturnErrorBadMD5` |
| JxBrowser 部件签名 | `~/.jxbrowser-8.5.0/Chromium/chrome.dll.sig`、`chromium.exe.sig`、`*.manifest` | 首次运行解包时做部件校验 |
| 用户身份 | `userauth.jar`：CAS `https://my.st.com/cas/login`、OAuth 回调 `https://stm32cube-ua.st.com/api/user_service/login/callback?code=`、`isAuthenticated/login/logout/handleCookies/getAuthInfo` | `login <email> <password>` CLI 直连；`login_with_gui` 走浏览器 |
| 遥测 | `analytics.jar` → `https://sw-center.st.com/packs/cubeanalytics/`、`https://www.google-analytics.com/collect`、广告位 `https://www.st.com/bin/st/getAd.json` | 受"隐私声明"门控；`user_analytics <0|1>` 可关，`AnalyticsUserPreferences` 记录同意状态（`ANALYTICS_LICENSE_*` opcode） |
| 许可文本 | `docs/TH_STM32CubeMX-SOFTWARE-LICENSE.txt`、`SLA0048`、`third_parties_plugins/.../LicenseX.txt`、`terms-of-use.html` 链接 | 第三方包各自带 license 资源（`PdscLicense`/`LicenseGlobal` 类） |
| 安全启动配置 | `projectmanager.security`（76 类）、`BootPathManager`、`OEMiRoTBootMatcher`、`RotXmlReader`、`ProvisioningFilesManagement`、`DaFactory`/`obKeysReaderH5/H7` | H5/H7RS 的 ROW/RoT/调试鉴权文件与 OB 密钥读写，依赖 `App Paths\STM32CubeProgrammer.exe` 定位烧写工具 |

## 4. 网络端点全集（产品自有，非第三方库噪声）

```
https://sw-center.st.com/packs/resource/            更新主站（SoftUpdates library/）
https://sw-center.st.com/packs/cube-finder-db/md5.xml
https://sw-center.st.com/packs/cubeanalytics/
https://mcucrossselector.codex.cro.st.com/          交叉选择服务（crossselector.cfg）
https://xsel.stmcufinder.com/                       同上（备用域名）
https://api.ultralibrarian.com/api/v1               价格/替代料（React 侧）
https://my.st.com/cas/login                         登录
https://stm32cube-ua.st.com/api/user_service/*      OAuth / 用户服务
https://eds.st.com/                                 电子设计服务（Help 入口）
https://artifacts.st.com/artifactory/mcd-cubemx-maven-local/   内部构件（DDR 服务等）
https://artifactory.st.com/artifactory/mcdmx-*      构建/分析包
https://citools.st.com/projects/microxplorer/sonarqube        内部质量门
https://wiki.st.com/stm32mcu/wiki/…                 帮助（Security/LPBAM/H7RS 等）
https://www.st.com/bin/st/getAd.json                广告位
https://www.google-analytics.com/collect            遥测
```

`db/plugins/updater/updaterThirdParties.xml`（244 KB）还内嵌了**每家第三方包的直链**
（如 `http://www.wolfSSL.com/files/ide/*.pack`、`https://download.quantropi.com/...`）
与 `PackDependencies`，即 CubeMX 会跳出 ST 域名下载第三方包。

## 5. 对 MCP 的实际影响

1. `login`/`logout`/`swmgr install` 会真的走网络；离线环境必须先用
   `swmgr set proxy type NO_PROXY` 或预先备好 Repository。
2. `project generate` 缺固件包时引擎会尝试下载 —— headless 无 UI 会挂起，
   因此 `project_generate` 先做完整性预检（`package.xml` + `Drivers/`）。
3. 遥测可以关：`runtime_props`/`ide_bridge action=analytics value=false`。
4. `product_db` 只以 `mode=ro` 打开 `cube-finder-db.db`，不写回。
5. 完整性相关命令（`import hackmxdb`、`bootpath wizard`、`pack validate`）保留为
   显式工具，因为它们是产品功能的一部分；调用后果由用户决定。
