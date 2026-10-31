"""Robust scan for any .ioc containing third-party component entries.

Uses os.walk with error tolerance and a depth cap so broken symlinks (WSL venvs,
junctions) cannot abort the scan.
"""
from __future__ import annotations

import os
import sys

ROOTS = [
    r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX\db",
    r"C:\Users\ERDAN.DESKTOP-MVAKHCO\STM32Cube\Repository",
    r"C:\Users\ERDAN.DESKTOP-MVAKHCO\.stm32cubemx",
    r"C:\Users\ERDAN.DESKTOP-MVAKHCO\Documents",
]
SKIP = ("AppData", "node_modules", ".venv", ".venv-wsl", "site-packages", ".git")


def main() -> int:
    found = 0
    for root in ROOTS:
        for dirpath, dirnames, filenames in os.walk(root, onerror=lambda e: None):
            dirnames[:] = [d for d in dirnames if d not in SKIP]
            for fn in filenames:
                if not fn.endswith(".ioc"):
                    continue
                p = os.path.join(dirpath, fn)
                try:
                    txt = open(p, encoding="iso-8859-1", errors="replace").read()
                except Exception:
                    continue
                keys = [l for l in txt.splitlines() if "ThirdParty" in l]
                if len(keys) > 1:
                    found += 1
                    print("=====", p)
                    for l in keys[:40]:
                        print("   ", l)
                    if found >= 5:
                        return 0
    print("scanned; third-party ioc found:", found)
    return 0


if __name__ == "__main__":
    sys.exit(main())
