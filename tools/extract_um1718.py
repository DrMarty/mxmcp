"""Extract the STM32CubeMX script/CLI reference pages from UM1718 into text."""
import sys
from pathlib import Path

import fitz

PDF = r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX\help\UM1718.pdf"
OUT = Path(__file__).resolve().parent.parent / "docs" / "um1718_script_api.txt"


def main() -> int:
    doc = fitz.open(PDF)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    keep = []
    for i in range(doc.page_count):
        text = doc[i].get_text()
        low = text.lower()
        if ("script" in low and "mcu" in low) or "loadproject" in low or \
           "generatecode" in low or "mgds." in low or "errordialog" in low:
            keep.append((i + 1, text))
    with OUT.open("w", encoding="utf-8") as fh:
        for page, text in keep:
            fh.write(f"\n\n===== PAGE {page} =====\n")
            fh.write(text)
    print(f"pages kept: {len(keep)} -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
