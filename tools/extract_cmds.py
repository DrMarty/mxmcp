"""Extract addCommand(...) registrations from a javap -c dump.

Each registration looks like:
    ldc ... // String <command>
    ldc ... // String <help text>
    iconst_N / bipush N
    new ...  // class <Listener>
    ...
    invokestatic ... CommandLineManager.addCommand

We walk backwards from each addCommand call and capture the nearest preceding
two String constants plus the argument count opcode.
"""
import re
import sys

path = sys.argv[1]
lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
out = []
for i, line in enumerate(lines):
    if "CommandLineManager.addCommand" in line:
        strings = []
        argc = None
        for j in range(i - 1, max(-1, i - 60), -1):
            m = re.search(r"// String (.*)$", lines[j])
            if m and len(strings) < 2:
                strings.append(m.group(1))
            m2 = re.search(r"^\s+\d+: (iconst_(\d)|bipush\s+(\d+))", lines[j])
            if m2 and argc is None:
                argc = m2.group(2) or m2.group(3)
            if len(strings) == 2 and argc is not None:
                break
        cmd = strings[-1] if strings else "?"
        helptext = strings[0] if len(strings) > 1 else ""
        out.append((cmd, helptext, argc))
for c, h, n in sorted(set(out)):
    print(f"{c!r:60} argc={n}  {h[:110]}")
print(f"-- total {len(out)} (unique {len(set(out))})")
