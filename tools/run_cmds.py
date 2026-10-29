import os
import subprocess
import sys

JAVA = r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX\jre\bin\java.exe"
EXE = r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX\STM32CubeMX.exe"
HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.abspath(os.path.join(HERE, "..", "probe"))


def run(lines, name, timeout=420, show=600):
    d = os.path.join(WORK, name)
    os.makedirs(d, exist_ok=True)
    # keep every produced file inside the probe folder: rewrite absolute paths
    here = os.path.abspath(os.path.join(HERE, ".."))
    lines = [l.replace(here, d) for l in lines]
    script = os.path.join(d, "s.txt")
    with open(script, "w", encoding="ascii") as fh:
        fh.write("\n".join(lines) + "\n")
    out = os.path.join(d, "out.log")
    with open(out, "wb") as fh:
        p = subprocess.Popen([JAVA, "-Djavax.net.ssl.trustStoreType=WINDOWS-ROOT",
                              "-jar", EXE, "-q", script],
                             stdout=fh, stderr=subprocess.STDOUT, cwd=d)
        try:
            p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            p.kill()
    txt = open(out, "rb").read().decode("utf-8", "replace")
    keep = [l for l in txt.splitlines()
            if not (l[:4].isdigit() and " [" in l[:40])
            and "Invalid condition id" not in l]
    print(f"\n########## {name} rc={p.returncode} (log {out})")
    print("\n".join(keep[:show]))
    return out


if __name__ == "__main__":
    run(sys.stdin.read().splitlines(), sys.argv[1] if len(sys.argv) > 1 else "adhoc",
        show=int(sys.argv[2]) if len(sys.argv) > 2 else 600)
