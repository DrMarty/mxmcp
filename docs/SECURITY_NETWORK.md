# Chain of Trust, Licensing and Network Surface (Forensics)

All entries come from the installer bytes, `javap` decompilation or `analysis/strings_report.json`
(constant-pool and resource scan of 54 774 entries). **No signature verification or chain validation was performed** —
what is recorded here is what the product "declares", not "whether it is correct".

---

## 1. Deliverable Identity

| Item | Value |
|---|---|
| `STM32CubeMX.exe` SHA-256 | `67b12576eed1c9544668b529458d87e6a9db600cf53492da1534afa8cf1ca0b8` |
| Size / type | 227 197 688 B, **PE32 (i386)**, no TLS/LOAD_CONFIG directory |
| imphash | `6011984d7c1f1b97a34d7517a498bff8` |
| Version resource | ProductName `STM32CubeMX`, FileDescription `MicroXplorer for STM32Cube`, FileVersion/ProductVersion **`6.15.0-RC4`**, LegalCopyright `STMicroelectronics`; launcher's own version `0.1.0.4` (Launch4j) |
| Signature block | `WIN_CERTIFICATE` at end of file @227 187 288, length 10 400, `certificate_type=2 (pkcs7)`, payload SHA-256 `2fe76035…3d784` |
| Signer | `STMicroelectronics International N.V.` (CH / Genève, private organization, registration no. 54298350), serial `0b12c8b575d0d6e16489812ce64cd7c5`, valid 2022-10-26 → **2025-10-25** |
| Issuing CA | `DigiCert Trusted G4 Code Signing RSA4096 SHA384 2021 CA1` (sha256WithRSA) |
| Timestamp | `DigiCert Timestamp 2024`, issued by `DigiCert Trusted G4 RSA4096 SHA256 TimeStamping CA` |
| Certificates in chain | 5 (including `DigiCert Trusted Root G4`, `DigiCert Assured ID Root CA`) |

> Conclusion: the signature is two-layer Authenticode (signature + timestamp). **Digest coverage and chain trustworthiness were not verified**,
> and the signing certificate has expired (the timestamp can still keep historical signatures valid).

## 2. Launcher Behavior (88 Imported Functions)

```
ADVAPI32  RegOpenKeyExA / RegQueryValueExA / RegEnumKeyExA / RegCloseKey   → locate the JRE in the registry
KERNEL32  CreateProcessA / WaitForSingleObject / GetExitCodeProcess        → launch java -jar
          FindResourceExA / LoadResource / LockResource                    → read embedded resources
          CreateMutexA                                                     → single instance
          GlobalMemoryStatusEx                                             → compute -Xmx
          SetEnvironmentVariableA / GetEnvironmentVariableA                → inject environment variables
          SetUnhandledExceptionFilter / FormatMessageA                     → error dialog
USER32    CreateWindowExA / LoadImageA / SetTimer / ShowWindow / MessageBoxA → startup splash
SHELL32   ShellExecuteA                                                    → open URL/file
msvcrt    _findfirst/_findnext/_open/_read/_chdir/fopen/fwrite             → unpacking and logging
```

In other words: **the EXE itself is a jar** (first local header at `0x13000`, central directory at `0xD2F0A03`, 54 774 entries);
`java -jar STM32CubeMX.exe` is equivalent to double-clicking it, and UM1718 documents this as well.

## 3. Integrity and "Licensing"-Related Mechanisms

| Mechanism | Evidence | Notes |
|---|---|---|
| Database integrity | `com.st.microxplorer.db.DataBaseIntegrity`, `ThirdPartyIntegrityChecker`, `IntegrityCheckThread` (app jar) | Validates the DB/third-party directories at startup; `import hackmxdb` is an official "hot-patch DB" switch left for vendors, which sets the validation state to modifiable |
| Pack validation | `ThirdPartyCheckIntegrity`, `ThirdPartyCheckPdscCondition` and other opcodes (`analysis/plugin_protocol.json`); `PdscPackages.checkPdscSchema(...)` + `PackXsdList` (XSD 1.4.0…1.6.3) | Downloaded `.pack` files go through MD5 + pdsc schema validation |
| Package allow/deny list | `db/plugins/updater/PacksControlFlags.xml` (65 KB, `<Flag name="Denied">`, e.g. all Keil DFPs) | The GUI/CLI refuses to enable certain packages based on this |
| Download validation | `ReleaseMD5/ReleaseSize` in `STMUpdaterDefinitions.xml`, `https://sw-center.st.com/packs/cube-finder-db/md5.xml` | Size + MD5; failures map to `Updater_ReturnErrorBadMD5` |
| JxBrowser component signatures | `~/.jxbrowser-8.5.0/Chromium/chrome.dll.sig`, `chromium.exe.sig`, `*.manifest` | Components are verified when unpacked on first run |
| User identity | `userauth.jar`: CAS `https://my.st.com/cas/login`, OAuth callback `https://stm32cube-ua.st.com/api/user_service/login/callback?code=`, `isAuthenticated/login/logout/handleCookies/getAuthInfo` | `login <email> <password>` CLI connects directly; `login_with_gui` goes through the browser |
| Telemetry | `analytics.jar` → `https://sw-center.st.com/packs/cubeanalytics/`, `https://www.google-analytics.com/collect`, ad slot `https://www.st.com/bin/st/getAd.json` | Gated by the "privacy statement"; can be turned off with `user_analytics <0|1>`; `AnalyticsUserPreferences` records consent state (`ANALYTICS_LICENSE_*` opcodes) |
| License texts | `docs/TH_STM32CubeMX-SOFTWARE-LICENSE.txt`, `SLA0048`, `third_parties_plugins/.../LicenseX.txt`, `terms-of-use.html` link | Each third-party package ships its own license resources (`PdscLicense`/`LicenseGlobal` classes) |
| Secure boot configuration | `projectmanager.security` (76 classes), `BootPathManager`, `OEMiRoTBootMatcher`, `RotXmlReader`, `ProvisioningFilesManagement`, `DaFactory`/`obKeysReaderH5/H7` | Reading/writing ROW/RoT/debug authentication files and OB keys for H5/H7RS; relies on `App Paths\STM32CubeProgrammer.exe` to locate the programming tool |

## 4. Complete Set of Network Endpoints (Product's Own, Not Third-Party Library Noise)

```
https://sw-center.st.com/packs/resource/            Main update site (SoftUpdates library/)
https://sw-center.st.com/packs/cube-finder-db/md5.xml
https://sw-center.st.com/packs/cubeanalytics/
https://mcucrossselector.codex.cro.st.com/          Cross-selection service (crossselector.cfg)
https://xsel.stmcufinder.com/                       Same as above (backup domain)
https://api.ultralibrarian.com/api/v1               Pricing/alternative parts (React side)
https://my.st.com/cas/login                         Login
https://stm32cube-ua.st.com/api/user_service/*      OAuth / user service
https://eds.st.com/                                 Electronic design services (Help entry)
https://artifacts.st.com/artifactory/mcd-cubemx-maven-local/   Internal artifacts (DDR service, etc.)
https://artifactory.st.com/artifactory/mcdmx-*      Build/analysis packages
https://citools.st.com/projects/microxplorer/sonarqube        Internal quality gate
https://wiki.st.com/stm32mcu/wiki/…                 Help (Security/LPBAM/H7RS, etc.)
https://www.st.com/bin/st/getAd.json                Ad slot
https://www.google-analytics.com/collect            Telemetry
```

`db/plugins/updater/updaterThirdParties.xml` (244 KB) also embeds **direct links for every third-party package**
(e.g. `http://www.wolfSSL.com/files/ide/*.pack`, `https://download.quantropi.com/...`)
and `PackDependencies`, i.e. CubeMX will go outside ST domains to download third-party packages.

## 5. Practical Impact on MCP

1. `login`/`logout`/`swmgr install` really do go over the network; offline environments must first use
   `swmgr set proxy type NO_PROXY` or have a Repository prepared in advance.
2. When `project generate` is missing a firmware package the engine will try to download it — headless with no UI it hangs,
   so `project_generate` runs an integrity pre-check first (`package.xml` + `Drivers/`).
3. Telemetry can be turned off: `runtime_props`/`ide_bridge action=analytics value=false`.
4. `product_db` only opens `cube-finder-db.db` with `mode=ro` and never writes back.
5. Integrity-related commands (`import hackmxdb`, `bootpath wizard`, `pack validate`) are kept as
   explicit tools because they are part of the product's functionality; the consequences of calling them are up to the user.
