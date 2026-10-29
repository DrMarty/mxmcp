"""Turn the plugin RPC constants into a structured protocol document.

`PluginViewConstants` holds every `getSpecificTask(int, Object)` opcode and the
return codes the host uses to talk to plugins (updater, thirdparty,
projectmanager, analytics, rtos...). This tool groups them by subsystem and
emits analysis/plugin_protocol.json plus a markdown table.
"""
from __future__ import annotations

import collections
import json
import re
import subprocess
import sys
from pathlib import Path

JAVAP = r"C:\Program Files\Eclipse Adoptium\jdk-21.0.10.7-hotspot\bin\javap.exe"
HERE = Path(__file__).resolve().parent.parent
JAR = HERE / "_extract" / "cubemx_full.jar"
OUT = HERE / "analysis"
CLS = "com.st.microxplorer.plugin.PluginViewConstants"

INT_RE = re.compile(r"static final int (\w+) = (-?\d+);")
STR_RE = re.compile(r'static final java\.lang\.String (\w+) = "([^"]*)";')


def main() -> int:
    OUT.mkdir(exist_ok=True)
    txt = subprocess.run([JAVAP, "-p", "-constants", "-cp", str(JAR), CLS],
                         capture_output=True, timeout=120).stdout.decode("utf-8", "replace")
    ints = INT_RE.findall(txt)
    strs = STR_RE.findall(txt)
    by_prefix: dict[str, dict[str, int]] = collections.defaultdict(dict)
    returns: dict[str, int] = {}
    for name, value in ints:
        v = int(value)
        if "Return" in name:
            returns[name] = v
            continue
        prefix = name.split("_")[0].replace("Updater", "updater")
        by_prefix[prefix][name] = v
    report = {
        "class": CLS,
        "opcode_groups": {k: dict(sorted(v.items(), key=lambda x: x[1]))
                          for k, v in sorted(by_prefix.items())},
        "return_codes": dict(sorted(returns.items(), key=lambda x: x[1])),
        "string_constants": dict(strs),
        "totals": {"opcodes": sum(len(v) for v in by_prefix.values()),
                   "return_codes": len(returns),
                   "string_constants": len(strs)},
    }
    (OUT / "plugin_protocol.json").write_text(json.dumps(report, indent=1),
                                              encoding="utf-8")
    for k, v in report["opcode_groups"].items():
        print(f"{k:26s} {len(v):4d} opcodes, max={max(v.values())}")
    print(f"return codes: {len(returns)}, strings: {len(strs)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
