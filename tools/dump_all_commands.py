"""Dump every CLI command registered across CubeMX plugin jars.

Strategy: search all class files in the plugins tree (and the main app jar) for
the constant-pool string "addCommand"; disassemble those classes with javap and
mine the ldc "String" pairs preceding each invokestatic addCommand call.
"""
import os
import re
import subprocess
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor

JAVAP = r"C:\Program Files\Eclipse Adoptium\jdk-21.0.10.7-hotspot\bin\javap.exe"
PLUGINS = r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX\plugins"
APPJAR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                      "_extract", "cubemx_app.jar")


def candidates():
    jars = {}
    for dp, _dn, fn in os.walk(PLUGINS):
        for f in fn:
            if f.endswith(".jar"):
                p = os.path.join(dp, f)
                jars[os.path.relpath(p, PLUGINS)] = p
    jars["__app__"] = APPJAR
    for rel, p in jars.items():
        try:
            z = zipfile.ZipFile(p)
        except Exception:
            continue
        names = []
        for n in z.namelist():
            if not n.endswith(".class"):
                continue
            b = z.read(n)
            if b"addCommand" in b:
                names.append(n[:-6].replace("/", "."))
        if names:
            yield rel, p, names


def analyze(javap_args):
    rel, jar, cls = javap_args
    cp = jar
    if rel != "__app__":
        cp = jar + os.pathsep + APPJAR
    try:
        p = subprocess.run([JAVAP, "-p", "-c", "-constants", "-cp", cp, cls],
                           capture_output=True, timeout=120)
    except subprocess.TimeoutExpired:
        return rel, cls, []
    txt = p.stdout.decode("utf-8", "replace")
    if p.returncode != 0:
        return rel, cls, []
    lines = txt.splitlines()
    found = []
    for i, line in enumerate(lines):
        if "CommandLineManager.addCommand" not in line:
            continue
        strings, argc = [], None
        for j in range(i - 1, max(-1, i - 80), -1):
            m = re.search(r"// String (.*)$", lines[j])
            if m and len(strings) < 2:
                strings.append(m.group(1))
            m2 = re.match(r"\s+\d+: (iconst_(\d)|bipush\s+(\d+))", lines[j])
            if m2 and argc is None:
                argc = m2.group(2) or m2.group(3)
            if len(strings) >= 2 and argc is not None:
                break
        if strings:
            found.append((" ".join(strings[-1].split()),
                          " ".join((strings[0] if len(strings) > 1 else "").split()),
                          argc))
    return rel, cls, found


def main() -> int:
    tasks = []
    for rel, jar, names in candidates():
        for c in names:
            tasks.append((rel, jar, c))
    print(f"classes to inspect: {len(tasks)}", file=sys.stderr)
    rows = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        for rel, cls, found in ex.map(analyze, tasks):
            for cmd, hlp, argc in found:
                rows.append((cmd, hlp, argc, rel, cls))
    seen = set()
    for cmd, hlp, argc, rel, cls in sorted(rows):
        key = (cmd, hlp)
        if key in seen:
            continue
        seen.add(key)
        print(f"{cmd!r}\targc={argc}\t{rel}\t{hlp[:120]}")
    print(f"-- rows {len(rows)}, unique {len(seen)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
