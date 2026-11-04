# Changelog

This project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and version numbers follow [Semantic Versioning](https://semver.org/).

## [1.1.0] — 2026-10-29

### Added: standalone mode (no CubeMX installation required)

* **Data pack** (`python -m mxmcp.bundle build`): 9.1 MB, 2 019 MCUs /
  245 083 pins (including remappable signals and GPIO IOModes) / 138 565 IP entries / 274 IP mode sets /
  215 boards / 1 756 template manifests / HAL Init parameter trees for 192 IPs.
* **Standalone engine** (`standalone.py`): maintains an in-memory project isomorphic to the `.ioc`, with real validation of
  pin-signal legality, signal uniqueness, IP existence, and mode legality; `IPParameters` are registered automatically.
* **Standalone code generation** (`codegen.py`): generates `main.c/main.h/`MSP`/
  IRQ/`Makefile` skeletons from the HAL Init parameter trees, with parameter values taken directly from the `.ioc`.
* When not installed, engine tools return an actionable error **immediately** instead of waiting for a JVM timeout.
* 12 new tools: `standalone_info/create/open/pin/signals/mode/param/nvic/view/
  validate/generate/mcu`.

### Added: completed reverse-engineering coverage

* **Full rebuild** of the embedded archive: 54 774 entries (previously only 12 666 were recovered), 0 failures;
  `com/st/components/**` (including `CommandLineManager`) statically decompiled for the first time.
* CLI registry expanded from 89 to **267** entries (64 command heads), each recording its registering class, arity, and help.
* Plugin protocol: **217 opcodes + 30 return codes** (`analysis/plugin_protocol.json`).
* Data plane: `db_schema` (elements/attributes/value domains of 6 690 XML files), condition expression language
  (**636 975** expressions, including `$IpInstance`/`Semaphore_*`/`MOD()`/`IF()`),
  `.ioc` grammar (506 sample files, **7 670** key patterns), template model (**2 706** variable keys),
  28 CubeIDE-MX services (mxScratch exchange format).
* Runtime: measured semantics of `dma`/`mdma`/`gic`/`NVIC` (15 verbs)/`MMT`/`import`/`selector`;
  found that `dma`/`NVIC` and others write results on log4j lines and that terminators can be glued onto lines; handled in `engine.py`.
* RTOS: `rtos_apis.xml` (CMSIS v1 7 classes / v2 8 classes, 75 fields) + object storage format
  `<PREFIX>.<List><nn>=v1,v2,…`, with 5 `rtos_*` tools implemented.
* Middleware: 36 instance names from `MiddleWareConstants` + template hooks, `middleware_list/add`.
* Trust chain and networking: Authenticode (ST signature/DigiCert timestamp/certificate validity period),
  updater sites and md5 verification, `PacksControlFlags` deny list, CAS/OAuth login endpoints.
* Other: `utilities` (STM32PackCreator, 4 823 classes), `Uninstaller` (IzPack),
  `olddb` (DB.6.0.141.tar.bz2), `third_parties_plugins` (20 p2 bundles).

### Added: open-source project infrastructure

* `LICENSE` (MIT + THIRD-PARTY NOTICES: ST-derived data is not distributed with the repository).
* `pyproject.toml` (zero runtime dependencies, two entry points: `mxmcp` / `mxmcp-bundle`).
* GitHub Actions: lint + protocol self-check + unit tests (Ubuntu/Windows × py3.9/3.11/3.12)
  + compliance check + wheel check.
* `tools/check_compliance.py`: CI blocks committing any ST-derived artifacts.
* Documentation: `ARCHITECTURE.md`, `DATA_MODEL.md`, `FEATURES.md` (feature coverage matrix),
  `STANDALONE.md`, `SECURITY_NETWORK.md`, `CLI_REGISTRY.md`.

### Fixed

* `engine.py`: three framing cases: terminator glued to a line (`...0 OK`), log4j responses, and glued prompts.
* `mode_set`: middleware IPs require the unquoted form; both forms are now tried and the log is returned in the result.
* `mode_list`: falls back to the db mode table when `get modes` returns KO for a middleware IP.
* `rtos_*`: merges default values from `project_ext.ioc` (CubeMX writes RTOS tables only in the extended save).
* `store.get`: falls back to the most recently used project when `project_id` is omitted.

## [1.0.0] — 2026-10-28

First usable release: 72 tools covering project lifecycle, selection, pins, clocks, peripheral parameters,
code generation, software packs, `.ioc` read/write, and CLI fallback; includes end-to-end and unit tests.
