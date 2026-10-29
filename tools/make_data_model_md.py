"""Generate docs/DATA_MODEL.md from the analysis extracts.

Everything in the document is produced from `analysis/*.json`, so the numbers and
the vocabularies are evidence, not prose copied by hand.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
A = HERE / "analysis"
DST = HERE / "docs" / "DATA_MODEL.md"
load = lambda n: json.loads((A / n).read_text(encoding="utf-8"))


def table(rows, headers):
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(c).replace("\n", " ") for c in r) + " |")
    return "\n".join(out)


def main() -> int:
    db = load("db_schema.json")
    cond = load("condition_language.json")
    ioc = load("ioc_grammar.json")
    tpl = load("template_model.json")
    srv = load("cubeide_services.json")
    finder = load("mcufinder_data_layer.json")
    census = load("install_census.json")
    api = load("api_index.json")

    L: list[str] = ["# CubeMX 数据模型（由安装件与运行时提取生成）", ""]
    L.append("本文全部由 `tools/*.py` 对安装件与运行中的引擎取证生成，原始记录在 "
             "`analysis/*.json`。任何写回的字段都必须能在本文找到出处。")
    L.append("")
    L.append("## 1. 资产规模")
    L.append(table(
        [(census["total_files"], f"{census['total_bytes']/1e6:.0f} MB",
          census["directory_count"],
          census["extensions"].get(".xml", 0), census["extensions"].get(".ftl", 0),
          census["extensions"].get(".ioc", 0), census["extensions"].get(".ld", 0),
          census["extensions"].get(".dtsi", 0) + census["extensions"].get(".dts", 0),
          len(api))
         for _ in range(1)],
        ["文件", "体积", "目录", "XML", "FTL", "IOC", "LD", "DTS(I)", "类"]))
    L.append("")

    L.append("## 2. XML 族谱（每族根元素与元素/属性计数）")
    rows = []
    for group, info in db.items():
        if not isinstance(info, dict) or "elements" not in info:
            continue
        roots = ", ".join(f"{k}×{v}" for k, v in list(info["roots"].items())[:4])
        elems = ", ".join(f"{k}×{v}" for k, v in list(info["elements"].items())[:8])
        rows.append((group, info["files_total"], roots or "-", elems))
    L.append(table(rows, ["目录族", "文件数", "根元素", "高频子元素"]))
    L.append("")

    L.append("## 3. MCU 记录字段（`db/mcu/*.xml`）")
    mcu = db["mcu"]
    attr_rows = []
    for el, attrs in list(mcu["attributes"].items())[:18]:
        keys = ", ".join(f"{k}×{v}" for k, v in list(attrs.items())[:8])
        attr_rows.append((el, keys))
    L.append(table(attr_rows, ["元素", "属性（出现次数）"]))
    L.append("")

    L.append("## 4. IP 模式文件（`db/mcu/IP/*_Modes.xml`）")
    ipm = db["mcu_ip_modes"]
    L.append(table([(el, n) for el, n in list(ipm["elements"].items())[:16]],
                   ["元素", "样本内出现次数"]))
    L.append("")
    L.append("`RefParameter@Type` 的实测取值集合（含厂商手写拼写变体，均为事实）：")
    L.append("```")
    L.append(", ".join(f"{k}×{v}" for k, v in sorted(
        cond["refparameter_types"].items(), key=lambda x: -x[1])[:26]))
    L.append("```")
    L.append("`PossibleValue@Action`：" + ", ".join(
        f"{k}×{v}" for k, v in sorted(cond["possiblevalue_actions"].items(),
                                      key=lambda x: -x[1])[:10]))
    L.append("")

    L.append("## 5. 条件表达式语言")
    L.append(f"- 样本内 `Condition@Expression` 总数：**{cond['condition_expressions']:,}"
             f"**（{cond['files']} 个文件，解析失败 {cond['parse_errors']}）")
    ops = [k for k in cond["operators_and_tokens"]
           if not k[0].isalpha() or k in ("true",)]
    L.append(f"- 运算符/字面量：`{'`, `'.join(ops[:12])}`")
    L.append(f"- 内置引用：`{'`, `'.join(list(cond['dollar_references'])[:8])}`")
    L.append(f"- 函数：`{'`, `'.join(list(cond['functions_used'])[:6])}`")
    L.append("- 语义：`&` 与、`|` 或、`!` 非、`=` 相等、`>`/`<` 比较；"
             "`$IpInstance`/`$IpNumber` 展开为当前实例；`Semaphore_*$IpInstance` 为资源信号量；"
             "`DIE###` 为 die 变体布尔；`OB_*` 为选定位。")
    L.append("")

    L.append("## 6. `.ioc` 语法（语料统计）")
    L.append(f"- 语料 **{ioc['corpus_files']}** 份 `.ioc`，键模式 **{len(ioc['key_patterns'])}** 种；"
             f"覆盖家族：{', '.join(ioc['families_in_corpus'][:14])} 等 "
             f"{len(ioc['families_in_corpus'])} 个。")
    top = list(ioc["key_patterns"].items())[:18]
    L.append(table([(k, v["count"], ", ".join(list(v["shapes"])[:3])) for k, v in top],
                   ["键模式", "出现次数", "值形态"]))
    L.append("- 索引列表根：" + ", ".join(ioc["indexed_list_roots"][:12]))
    L.append("- 值内 `:` 转义为 `\\:`；`NVIC.<IRQ>` 与 `SH.*` 为转义高发键：" +
             ", ".join(ioc["escaped_value_keys"][:6]))
    L.append("")

    L.append("## 7. 代码生成模板")
    L.append(f"- 模板 **{tpl['template_count']}** 个，模型键 **{len(tpl['model_keys'])}** 个。")
    L.append("- 高频模型键：" + ", ".join(f"`{k}`" for k in list(tpl["model_keys"])[:24]))
    L.append("- include 图（节选）：")
    for k, v in list(tpl["include_graph"].items())[:5]:
        L.append(f"  - `{k}` → {', '.join(v[:6])}")
    L.append("")

    L.append("## 8. CubeIDE-MX 服务（工程/构建生成的真正后端）")
    rows = []
    for bundle, msgs in list(srv["services"].items()):
        names = sorted(k for k in msgs if k.endswith("Service"))
        rows.append((bundle.split("_")[0][:56], len(msgs), ", ".join(names[:8])))
    L.append(table(rows, ["p2 插件", "消息条数", "服务类（节选）"]))
    L.append(f"- mxScratch schema：`{Path(srv['mxscratch_schema_file']).name if srv['mxscratch_schema_file'] else '-'}`，"
             f"根元素：{', '.join(e['name'] for e in srv['mxscratch_schema']['root_elements'][:12])} …")
    L.append("")

    L.append("## 9. 选型数据库（`~/.stmcufinder/plugins/mcu/cube-finder-db.db`）")
    fdb = finder["finder_db"]
    if fdb.get("tables"):
        L.append(f"- {Path(fdb['path']).name}，{fdb['bytes']/1e6:.0f} MB，"
                 f"{len(fdb['tables'])} 张表（只读取证）")
        L.append(table([(t, v["rows"], ", ".join(v["columns"])[:90])
                        for t, v in list(fdb["tables"].items())],
                       ["表", "行数", "列"]))
    else:
        L.append("- 本机未下载（由 CubeMX 的数据库刷新获取）")
    L.append(f"- React↔Java 桥方法：{', '.join(sorted(finder['bridge_function_frequency']))}")
    L.append("")
    DST.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("wrote", DST.name, DST.stat().st_size, "bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
