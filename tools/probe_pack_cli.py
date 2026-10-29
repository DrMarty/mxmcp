"""Introspect the pack/third-party plugins that hold the CMSIS-Pack commands."""
from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path

JAVAP = r"C:\Program Files\Eclipse Adoptium\jdk-21.0.10.7-hotspot\bin\javap.exe"
P = Path(r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX\plugins")
APP = Path(__file__).resolve().parent.parent / "_extract" / "cubemx_app.jar"


def classes_with(jar: Path, needles: tuple[bytes, ...]) -> list[str]:
    out = []
    try:
        z = zipfile.ZipFile(jar)
    except Exception:
        return out
    for n in z.namelist():
        if not n.endswith(".class"):
            continue
        b = z.read(n)
        if all(x in b for x in needles):
            out.append((jar, n[:-6].replace("/", ".")))
    return out


def javap(jar: Path, cls: str, extra: list[str] | None = None) -> str:
    cp = str(jar) if jar != APP else str(APP)
    args = [JAVAP, "-p", "-c", *(["-constants"] if extra is None else []), "-cp", cp, cls]
    p = subprocess.run(args, capture_output=True, timeout=180)
    return p.stdout.decode("utf-8", "replace")


def main() -> int:
    target = P / "thirdparty.jar"
    hits = classes_with(target, (b"pack enable",))
    print("classes with 'pack enable':", [c for _, c in hits][:10])
    for jar, cls in hits[:3]:
        text = javap(jar, cls)
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if "// String pack" in line or "// String Pack" in line:
                print("\n".join(lines[max(0, i - 2):i + 6]))
                print("-----")
        out = Path("docs") / f"{cls.split('.')[-1]}.javap.txt"
        out.write_text(text, encoding="utf-8")
        print("saved", out, len(lines), "lines")
    return 0


if __name__ == "__main__":
    sys.exit(main())
