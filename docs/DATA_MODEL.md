# CubeMX 数据模型（由安装件与运行时提取生成）

本文全部由 `tools/*.py` 对安装件与运行中的引擎取证生成，原始记录在 `analysis/*.json`。任何写回的字段都必须能在本文找到出处。

## 1. 资产规模
| 文件 | 体积 | 目录 | XML | FTL | IOC | LD | DTS(I) | 类 |
|---|---|---|---|---|---|---|---|---|
| 11378 | 1520 MB | 709 | 6775 | 1756 | 504 | 277 | 134 | 3222 |

## 2. XML 族谱（每族根元素与元素/属性计数）
| 目录族 | 文件数 | 根元素 | 高频子元素 |
|---|---|---|---|
| mcu | 2019 | rules×2, Families×1, Mcu×37 | Peripheral×59606, Signal×10496, Core×2941, Flash×2720, Mcu×2711, Ram×2711, IONb×2711, Frequency×2026 |
| mcu_ip_modes | 1321 | IP×30 | PossibleValue×23362, RefParameter×7994, Condition×5061, Parameter×3882, Description×2642, Semaphore×1861, Mode×1793, RefMode×1322 |
| mcu_configs | 1308 | IP×30 | Argument×8763, MethodArg×845, LibMethod×317, CallLibMethod×314, RefConfig×305, IFCondition×185, File×154, ImplementCallBack×60 |
| mcu_memory | 47 | rzone×20 | memory×180, mpc×51, mpcwm×47, provisioning×31, region×30, processor×22, rzone×20, device×20 |
| mcu_packs_vpdsc | 19 | package×10 | description×67, component×54, files×54, file×54, accept×39, condition×31, package×11, vendor×10 |
| families | 1 | Families×1 | Peripheral×59606, Core×2904, Mcu×2674, Ram×2674, IONb×2674, Flash×2674, Frequency×2016, Temperature×1990 |
| rules | 1 | rules×1 | br×337, match×234, rule×117, diagnostic×117, condition×8, result×7, rules×1 |
| compatibility | 1 | rules×1 | rule×317, description×317, MXDBVersion×317, SeparatorOnValue×317, MatcherOnKey×316, MatcherPattern×315, MatchToPattern×312, ParserCondition×247 |
| boardmanager_pdsc | 10 | package×10 | feature×2250, book×333, description×228, compatibleDevice×222, board×215, mountedDevice×215, image×184, debugInterface×176 |
| updater | 3 | PacksControlFlags×1, Packages×2 | FirmwareRelease×916, PackDescription×763, Note×695, Flag×645, Firmware×398, ThirdParty×264, ShortDescription×264, Pack×229 |
| power | 225 | Battery×1, Consumption×19 | Consumption×1921, Oscillator×1902, Foscillator×1902, FCPU×1902, Mode×373, Vcore×226, Category×147, Key×147 |
| clock_plugin | 64 | Clock×64 | Label×10716, Input×10419, Output×9414, Element×5962, Signal×4069, Condition×2309, Background×442, Tree×198 |
| projectmanager | 2 | project×1, Toulchains×1 | name×214, state×202, option×200, Family×167, version×40, Families×17, settings×10, archiveVersion×10 |
| contextual | 364 | ctx_periph_help×20 | ctx_periph_help×20, serie×20, peripheral×20, title×20, extract×20, help_text×20, mode×20, config×20 |
| templates_dirs | 656 | - |  |
| all_xml_files | 6690 | ctx_periph_help×178, ctx_core_help×1, ctx_pinout_help×184, ctx_serie_help×1 | Signal×1377957, Argument×618180, PossibleValue×445203, Parameter×277028, RefParameter×262101, ContextIP×252757, Pin×245083, Condition×232596 |

## 3. MCU 记录字段（`db/mcu/*.xml`）
| 元素 | 属性（出现次数） |
|---|---|
| rule | name×317, cache×117 |
| Families | {http://www.w3.org/2001/XMLSchema-instance}noNamespaceSchemaLocation×1 |
| Family | Name×27 |
| SubFamily | Name×125 |
| Mcu | RefName×2711, Name×2674, PackageName×2674, RPN×2674, Visible×48, ClockTree×37, DBVersion×37, Family×37 |
| Voltage | Max×1998, Min×1989 |
| Temperature | Max×1998, Min×1998 |
| Peripheral | Type×59606, MaxOccurs×59606 |
| Current | Run×1617, Lowest×1469 |
| IP | InstanceName×1181, Name×1181, Version×1181, ConfigFile×866, ClockEnableMode×237 |
| Pin | Name×1379, Position×1379, Type×1379, Variant×110 |
| Signal | Name×10496, IOModes×1242 |
| Condition | Diagnostic×27, Expression×27 |

## 4. IP 模式文件（`db/mcu/IP/*_Modes.xml`）
| 元素 | 样本内出现次数 |
|---|---|
| PossibleValue | 23362 |
| RefParameter | 7994 |
| Condition | 5061 |
| Parameter | 3882 |
| Description | 2642 |
| Semaphore | 1861 |
| Mode | 1793 |
| RefMode | 1322 |
| Signal | 1283 |
| SignalLogicalOp | 1036 |
| RefSignal | 927 |
| ModeLogicOperator | 787 |
| ConfigForMode | 617 |
| IP | 30 |
| About | 29 |

`RefParameter@Type` 的实测取值集合（含厂商手写拼写变体，均为事实）：
```
list×132600, string×52947, integer×36605, double×6215, stringRW×5536, boolean×4746, hex×4283, String×4035, List×2407, uniqueElementList×1824, ×1799, UniqueElementList×1725, integerReadOnly×1458, StringRW×1375, Array×1247, Integer×740, decimal×531, subtitle×440, RWstring×434, Hex×319, StringHex×122, Int×94, doubleReadOnly×60, int×45, polynomialodd×30, bool×16
```
`PossibleValue@Action`：Disable×51083, Remove×3705, DISABLE×2036, ENABLE×1251, remove×1165, disable×339, FLASH_BB_PRIV×40, FLASH_BB_SEC×40, 0×34, EXTMEM_LINK_CONFIG_1LINE×24

## 5. 条件表达式语言
- 样本内 `Condition@Expression` 总数：**636,975**（2629 个文件，解析失败 0）
- 运算符/字面量：`(`, `)`, `|`, `=`, `&`, `!`, `$IpNumber`, `>`, `<`, `true`, `$IpInstance`, `:`
- 内置引用：`$IpInstance`, `$IpNumber`, `$IpInstanceCH0`, `$IpInstanceCH1`, `$IpInstanceCH2`, `$IpInstanceCH3`, `$IpInstanceCH7`, `$IpInstanceCH6`
- 函数：`MOD`, `IF`
- 语义：`&` 与、`|` 或、`!` 非、`=` 相等、`>`/`<` 比较；`$IpInstance`/`$IpNumber` 展开为当前实例；`Semaphore_*$IpInstance` 为资源信号量；`DIE###` 为 die 变体布尔；`OB_*` 为选定位。

## 6. `.ioc` 语法（语料统计）
- 语料 **506** 份 `.ioc`，键模式 **7670** 种；覆盖家族：STM32C0, STM32F0, STM32F1, STM32F2, STM32F3, STM32F4, STM32F7, STM32G0, STM32G4, STM32H5, STM32H7, STM32L0, STM32L1, STM32L4 等 26 个。
| 键模式 | 出现次数 | 值形态 |
|---|---|---|
| Mcu.PinN | 30896 | token, text |
| PIN.Signal | 30289 | token, text |
| PIN.Locked | 27887 | bool |
| PIN.GPIOParameters | 25354 | token, comma-list |
| PIN.GPIO_Label | 23013 | token, text |
| PIN.Mode | 10534 | token, text, colon-escaped |
| PIN.PinAttribute | 5908 | token, comma-list, empty |
| PIN.GPIO_PuPd | 4791 | token |
| Mcu.IPN | 4704 | token, text |
| PIN.GPIO_Speed | 4103 | token |
| PIN.GPIO_Mode | 3742 | token |
| SH.FMC_AN.0 | 1368 | token, comma-list |
| SH.FMC_AN.ConfNb | 1368 | int |
| SH.GPXTIN.0 | 1125 | token |
| SH.GPXTIN.ConfNb | 1125 | int |
| SH.FMC_DN.0 | 672 | token, comma-list |
| SH.FMC_DN.ConfNb | 672 | int |
| File.Version | 506 | int |
- 索引列表根：PIN.Signal, PIN.Locked, PIN.GPIOParameters, PIN.GPIO_Label, PIN.Mode, PIN.PinAttribute, PIN.GPIO_PuPd, PIN.GPIO_Speed, PIN.GPIO_Mode, PIN.GPIO_Speed_High_Default, PIN.GPIO_ModeDefaultOutputPP, PIN.GPIO_ModeDefaultEXTI
- 值内 `:` 转义为 `\:`；`NVIC.<IRQ>` 与 `SH.*` 为转义高发键：NVIC.SysTick_IRQn, NVIC.HardFault_IRQn, NVIC.NonMaskableInt_IRQn, NVIC.PendSV_IRQn, NVIC.BusFault_IRQn, NVIC.DebugMonitor_IRQn

## 7. 代码生成模板
- 模板 **1753** 个，模型键 **600** 个。
- 高频模型键：`definition`, `fargument`, `SERVICE_SHORT_NAME_UpperCase`, `SvcNbr`, `argument`, `characteristic`, `used_api`, `FamilyName`, `method`, `instanceIndex`, `myHash`, `initVector`, `name`, `variable`, `mode`, `argValue`, `i`, `words`, `index2`, `instName`, `IpInstance`, `ipName`, `args`, `argument2`
- include 图（节选）：

## 8. CubeIDE-MX 服务（工程/构建生成的真正后端）
| p2 插件 | 消息条数 | 服务类（节选） |
|---|---|---|
| com.st.stm32cube.ide.common.services.adapted | 18 | BuildSetupService, BuildUpdateService, DebugSetupService, DebugUpdateService, DeviceTreeSetupService, LinkSetupService, LinkUpdateService, ProjectRootModeSetupService |
| com.st.stm32cube.ide.common.services.mx.rcp | 1 |  |
| com.st.stm32cube.ide.common.services.mx | 29 | BuildSetupService, BuildSetupUpdateService, BuildUpdateService, CleanupService, CommonInputsCheckService, DebugUpdateService, DeviceTreeSetupService, IndexerService |
| com.st.stm32cube.ide.common.services | 13 | BuildSetupService, BuildUpdateService, DebugSetupService, DebugUpdateService, LinkSetupService, LinkUpdateService, ProjectSetupService, VersionTestService |
| com.st.stm32cube.ide.mcu.linker | 3 |  |
| com.st.stm32cube.ide.mcu.productdb | 1 |  |
- mxScratch schema：`mxScratch_v30.xsd`，根元素：startup, sourceEntry, sourceEntriesToRemove, sourceEntries, optimization, name, memory, memories, lib, inctoremove, include, icfloc …

## 9. 选型数据库（`~/.stmcufinder/plugins/mcu/cube-finder-db.db`）
- cube-finder-db.db，86 MB，19 张表（只读取证）
| 表 | 行数 | 列 |
|---|---|---|
| attribute | 232 | id:INTEGER, name:varchar(255), sourceName:varchar(255), type:varchar(45), unit:varchar(45) |
| cpn | 17491 | id:INTEGER, cpn:varchar(45), refname:TEXT, prmis_id:INT |
| cpn_has_attribute | 644828 | cpn_id:INTEGER, attribute_id:INTEGER, strValue:varchar(1024), numValue:double |
| cpn_relates_to_cpn | 0 | cpn_source_id:INTEGER, cpn_target_id:INTEGER, subcategory_id:INTEGER, manufacturer:TEXT |
| cts_origin | 0 | cpn_id:INTEGER, br_name:varchar(1024) |
| feature | 1807 | id:INTEGER, name:varbinary(1024) |
| featureitem | 5482 | id:INTEGER, item:varbinary(1024) |
| prmis_class | 30 | id:INTEGER, class_descr:varchar(255) |
| prmis_class_has_attribute | 514 | prmis_class_id:INTEGER, attribute_id:INTEGER, description:TEXT, shownInResTable:INTEGER, c |
| resource | 2766 | id:INTEGER, path:varchar(255), title:varchar(255), alternateName:varchar(100), fileType:va |
| rpn | 14550 | id:INTEGER, rpn:varchar(45), class_id:INTEGER, published:INTEGER, publishingState:varchar( |
| rpn_has_attribute | 143130 | rpn_id:INTEGER, attribute_id:INTEGER, strValue:varchar(1024), numValue:double |
| rpn_has_cpn | 17839 | rpn_id:INTEGER, cpn_id:INTEGER |
| rpn_has_featurelist | 79680 | rpn_id:INTEGER, feature_id:INTEGER, featureItem_id:INTEGER, feature_rank:INTEGER, item_ran |
| rpn_has_resource | 180755 | rpn_id:INTEGER, resource_id:INTEGER, subcategory_id:INTEGER |
| rpn_relates_to_rpn | 79983 | rpn_source_id:INTEGER, rpn_target_id:INTEGER, subcategory_id:INTEGER, manufacturer:TEXT |
| sqlite_sequence | 7 | name:, seq: |
| subcategory | 50 | id:INTEGER, itemKind:varchar(255), categoryRef:varchar(255), categoryName:varchar(255), su |
| version | 1 | id:INTEGER, data_model_version:TEXT, configuration_version:TEXT, latest_data_refresh:DATET |
- React↔Java 桥方法：getCustomPinsAsString, getOnlyCustomPinsAsString, getStandardPinsAsString

