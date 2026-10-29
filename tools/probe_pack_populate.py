"""How does an X-CUBE pack end up as a selectable third-party component?

Chain established so far:
  ThirdPartyModel.updateSwPack(xml)  -> ModelPack.setDownloaded(PackStatus.convert(xml.getPopulate()))
  ComponentItem.canBeSelected        -> packIsDownloaded && !packIsIntegrated && !packHasErrors
                                        && packIsDeviceCompatible && isDeviceCompatible && isEnabled

So `getPopulate()` of the XmlPack must be a usable status. This probe finds who
populates XmlPack (PackLoader / AbstractThirdPartyUpdaterManager) and what the
populate values mean, then checks the live model through `pack status`.

Also dumps PackStatus.convert and the updater's populate path.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

JAVAP = r"C:\Program Files\Eclipse Adoptium\jdk-21.0.10.7-hotspot\bin\javap.exe"
TP = r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX\plugins\thirdparty.jar"
OUT = Path("docs")


def javap(cls: str) -> str:
    txt = subprocess.run([JAVAP, "-p", "-c", "-constants", "-cp", TP, cls],
                         capture_output=True, timeout=240).stdout.decode("utf-8", "replace")
    OUT.mkdir(exist_ok=True)
    (OUT / f"{cls.split('.')[-1]}.javap.txt").write_text(txt, encoding="utf-8")
    return txt


def strings(txt: str) -> list[str]:
    return sorted(set(re.findall(r"// String (.*)$", txt, re.M)))


def main() -> int:
    for cls in [
        "com.st.microxplorer.plugins.thirdparty.model.PackStatus",
        "com.st.microxplorer.plugins.thirdparty.engine.PackLoader",
        "com.st.microxplorer.plugins.thirdparty.AbstractThirdPartyUpdaterManager",
        "com.st.microxplorer.plugins.thirdparty.ThirdPartyApiDb",
    ]:
        try:
            txt = javap(cls)
        except Exception as exc:  # noqa: BLE001
            print(cls, "FAILED", exc)
            continue
        print(f"===== {cls} ({len(txt)} bytes)")
        for s in strings(txt):
            print("   ", s[:140])
    return 0


if __name__ == "__main__":
    sys.exit(main())
