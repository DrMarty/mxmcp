"""Decode how pack-enable builds and validates its component selection.

The CLI path is: onCommandEntered -> applyFiltersFromCommandArguments ->
findComponent -> canBeSelected -> changeComponentState(true).
Understanding `onCommandEntered` shows which model objects must exist (the GUI
Controller) before a headless command can succeed.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

JAVAP = r"C:\Program Files\Eclipse Adoptium\jdk-21.0.10.7-hotspot\bin\javap.exe"
TP = Path(r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX\plugins\thirdparty.jar")
CLS = "com.st.microxplorer.plugins.thirdparty.cli.ThirdPartyCli"


def main() -> int:
    txt = subprocess.run([JAVAP, "-p", "-c", "-constants", "-cp", str(TP), CLS],
                         capture_output=True, timeout=180).stdout.decode("utf-8", "replace")
    Path("docs/ThirdPartyCli.full.txt").write_text(txt, encoding="utf-8")
    m = re.search(r"public boolean onCommandEntered\(java\.lang\.String\[\]\);(.*?)\n\n", txt, re.S)
    if m:
        print("=== onCommandEntered ===\n", m.group(1)[:3000])
    m = re.search(r"private com\.st\.microxplorer\.plugins\.thirdparty\.gui\.controller\.FilterController ([^\n]*)\n", txt)
    print("controller accessor:", m.group(0) if m else None)
    # find where controller is assigned
    for mm in re.finditer(r"(putfield|getfield).*#\d+\s+// Field controller.*", txt):
        pass
    i = txt.find("FilterController controller")
    print(txt[i - 200:i + 200] if i > 0 else "no field decl")
    # constructor body
    m = re.search(r"ThirdPartyCli\(com\.st\.microxplorer\.plugins\.thirdparty\.model\.ThirdPartyModel\);(.*?)\n\n", txt, re.S)
    if m:
        print("=== constructor ===\n", m.group(1)[:3000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
