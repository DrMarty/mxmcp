"""Recover the JxBrowser <-> React bridge used by the MCU Finder UI.

CubeMX embeds Chromium (JxBrowser) and loads a React bundle. Java exposes objects
to JS via `browser.profiles()`/`setJavascriptEnabled` + `addMessageReceiver` or the
legacy `window.java` injection. This tool scans:
  * the Java side for injected object names / message channel names
  * the shipped JS bundles for the matching calls
so the whole front-end contract is documented without executing the UI.
"""
from __future__ import annotations

import json
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path

ROOT = Path(r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX")
HERE = Path(__file__).resolve().parent.parent
JAR = HERE / "_extract" / "cubemx_full.jar"
OUT = HERE / "analysis" / "jxbrowser_bridge.json"

JS_BRIDGE = re.compile(
    r"(window\.(?:java|mx[a-zA-Z]*|STM32CubeMX|JxBrowser\w*|reactNative\w*)"
    r"|jxbrowser\.\w+|messageReceiver\w*|addMessageReceiver\w*"
    r"|registerAsync\w*|registerRouterHandler|executeJavaScript|provide\(\s*\"[^\"]+\")")
JS_URLS = re.compile(r"[\"'`](https?://[^\"'`]{6,120}|/(?:api|export|mcu|search)[^\"'`]{0,60})[\"'`]")
JAVA_BRIDGE = re.compile(r"(setJavascriptEnabled|addMessageReceiver|provide|executeJavaScript"
                         r"|registerRouterHandler|toJavaScript|JavaScript|window\.java)")


def main() -> int:
    report: dict = {"js": {}, "java": {}, "totals": {}}
    js_hits: Counter = Counter()
    urls: Counter = Counter()
    files: Counter = Counter()
    for d in ("reactClient", "reactClient1"):
        base = ROOT / "db" / "plugins" / "mcufinder" / d
        for p in sorted(base.rglob("*.js")) if base.exists() else []:
            text = p.read_text(encoding="utf-8", errors="replace")
            found = JS_BRIDGE.findall(text)
            for f in found:
                js_hits[f] += 1
            for u in JS_URLS.findall(text):
                urls[u] += 1
            files[d] += 1
            report["js"][f"{d}/{p.name}"] = {
                "bytes": p.stat().st_size,
                "bridge_hits": len(found),
                "unique_bridge": sorted(set(found))[:20],
                "urls": sorted(set(JS_URLS.findall(text)))[:40],
            }
    java_hits: Counter = Counter()
    if JAR.exists():
        z = zipfile.ZipFile(JAR)
        for n in z.namelist():
            if not n.startswith("com/st/microxplorer/mcufinder") or not n.endswith(".class"):
                continue
            b = z.read(n)
            strs = [s.decode("utf-8", "replace") for s in
                    re.findall(rb"[ -~]{6,120}", b)]
            bridge = [s for s in strs if "window." in s or "javascript" in s.lower()
                      or s.startswith("execute")]
            if bridge:
                java_hits[n] += 1
                report["java"][n[:-6].replace("/", ".")] = sorted(set(bridge))[:25]
    report["totals"] = {"js_files": dict(files), "bridge_tokens": dict(js_hits),
                        "js_urls": dict(urls.most_common(60)),
                        "java_classes": len(report["java"])}
    OUT.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print("js files:", dict(files))
    print("bridge tokens:", dict(js_hits))
    print("urls:", [u for u, _ in urls.most_common(20)])
    print("java classes with bridge literals:", list(report["java"])[:6])
    return 0


if __name__ == "__main__":
    sys.exit(main())
