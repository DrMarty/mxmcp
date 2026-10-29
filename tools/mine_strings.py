"""Cross-cutting string mining over the whole product.

Collects, per jar:
  * URLs / hostnames (server endpoints the product talks to)
  * file-name & extension literals (formats it reads/writes)
  * registry keys & windows paths (installer/OS integration)
  * system properties (`System.getProperty` keys) and env vars
  * log4j logger names are skipped; only printable ASCII runs >= 4

Writes analysis/strings_report.json. This is how the updater protocol, the
.ioc/.mw/.csv formats, and every hardcoded path get documented from evidence.
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
OUT = HERE / "analysis"
JAR_CANDIDATES = [HERE / "_extract" / "cubemx_full.jar"] + \
    sorted((ROOT / "plugins").glob("*.jar")) + \
    sorted((ROOT / "plugins" / "ip").glob("*.jar")) + \
    sorted((ROOT / "utilities").glob("**/*.jar"))

PRINTABLE = re.compile(rb"[\x20-\x7e]{4,200}")
URL = re.compile(r"(?:https?|ftps?|file|jar|tcp|ssl)://[^\s\"'<>|]{4,200}")
HOST = re.compile(r"\b[a-z0-9][a-z0-9.-]*\.(?:com|net|org|io|eu|st)\b")
EXT = re.compile(r"\.[A-Za-z0-9]{1,6}\b")
PROP = re.compile(r"^[a-z][a-z0-9]*(?:\.[a-z0-9_\-]+){1,}$")
ENVVAR = re.compile(r"^[A-Z][A-Z0-9_]{2,}$")


def cp_strings(data: bytes) -> list[str]:
    """All UTF8 constants from a class file's constant pool."""
    if data[:4] != b"\xca\xfe\xba\xbe":
        return []
    count = int.from_bytes(data[8:10], "big")
    pos = 10
    out: list[str] = []
    i = 1
    while i < count:
        tag = data[pos]
        pos += 1
        if tag == 1:
            ln = int.from_bytes(data[pos:pos + 2], "big")
            pos += 2
            raw = data[pos:pos + ln]
            pos += ln
            try:
                out.append(raw.decode("utf-8"))
            except UnicodeDecodeError:
                out.append(raw.decode("latin-1"))
        elif tag in (7, 8, 16, 19, 20):
            pos += 2
        elif tag == 15:
            pos += 3
        elif tag in (3, 4, 9, 10, 11, 12, 17, 18):
            pos += 4
        elif tag in (5, 6):
            pos += 8
            i += 1
        else:
            break
        i += 1
    return out


def main() -> int:
    OUT.mkdir(exist_ok=True)
    urls: dict[str, list[str]] = {}
    hosts: Counter = Counter()
    exts: Counter = Counter()
    props: Counter = Counter()
    envs: set[str] = set()
    files: Counter = Counter()
    reg: Counter = Counter()
    per_class_urls: dict[str, list[str]] = {}
    for jar in JAR_CANDIDATES:
        if not jar.exists():
            continue
        key = "app" if jar.name == "cubemx_full.jar" else jar.name
        z = zipfile.ZipFile(jar)
        for n in z.namelist():
            data = z.read(n)
            if n.endswith(".class"):
                strings = cp_strings(data)
            elif n.endswith((".xml", ".properties", ".txt", ".MF", ".json", ".ftl")):
                strings = [m.group().decode("ascii", "replace")
                           for m in PRINTABLE.finditer(data)]
            else:
                continue
            found_urls = set()
            for s in strings:
                for u in URL.findall(s):
                    found_urls.add(u)
                    hosts.update(HOST.findall(u))
                for m in HOST.findall(s):
                    if "st.com" in m or "stm" in m or ".org" in m:
                        hosts[m] += 0 if m in hosts else 1
                if PROP.match(s) and ("st." in s or "cubemx" in s or "stm32" in s
                                       or "java." in s or "os." in s or "user." in s
                                       or "javax." in s or "sun." in s):
                    props[s] += 1
                if ENVVAR.match(s) and len(s) > 4 and not s.endswith(".class"):
                    envs.add(s)
                if s.startswith(("SOFTWARE\\", "HKEY_", "CurrentVersion",
                                 "HKLM", "HKCU")):
                    reg[s] += 1
                if re.fullmatch(r"[\w.\-\\/%]{2,80}\.(?:ioc|mw|xml|csv|ftl|txt|pdf|"
                                r"html?|jar|zip|pack|pdsc|vpdsc|def|log|json|properties|"
                                r"ser|idx|pidx|md5)", s):
                    files[s] += 1
                for e in EXT.findall(s) if len(s) < 40 else []:
                    exts[e.lower()] += 1
            if found_urls:
                urls.setdefault(key, []).extend(sorted(found_urls))
                per_class_urls[f"{key}::{n}"] = sorted(found_urls)
    urls = {k: sorted(set(v)) for k, v in urls.items()}
    report = {
        "urls_by_jar": urls,
        "hosts": sorted(hosts),
        "filenames": [f for f, _ in files.most_common(400)],
        "system_properties": [p for p, _ in props.most_common(200)],
        "env_vars": sorted(envs),
        "registry": [r for r, _ in reg.most_common(100)],
        "classes_with_urls": per_class_urls,
    }
    (OUT / "strings_report.json").write_text(json.dumps(report, indent=1),
                                             encoding="utf-8")
    print(f"hosts: {len(report['hosts'])}, urls: {sum(len(v) for v in urls.values())}, "
          f"props: {len(report['system_properties'])}, env: {len(report['env_vars'])}")
    print("hosts sample:", report["hosts"][:25])
    return 0


if __name__ == "__main__":
    sys.exit(main())
