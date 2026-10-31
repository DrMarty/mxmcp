"""Load an .ioc project, apply edits through the CubeMX CLI, save and generate.

This is the exact command dialect the MCP server will drive. It exists as a
standalone harness so the behaviour can be reproduced without the MCP layer.
"""
import json
import subprocess
import sys
from pathlib import Path

JAVA = r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX\jre\bin\java.exe"
EXE = r"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeMX\STM32CubeMX.exe"


def run_mx(workdir: Path, commands: list[str], timeout: int = 240) -> tuple[int, list[str]]:
    workdir.mkdir(parents=True, exist_ok=True)
    script = workdir / "mx_script.txt"
    script.write_text("\n".join(commands) + "\n", encoding="ascii")
    log = workdir / "mx_console.log"
    with log.open("wb") as fh:
        proc = subprocess.Popen([JAVA, "-jar", EXE, "-q", str(script)],
                                stdout=fh, stderr=subprocess.STDOUT, cwd=str(workdir))
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
    text = log.read_text(encoding="utf-8", errors="replace").splitlines()
    clean = [l for l in text
             if " [INFO" not in l and " [WARN" not in l and " [ERROR" not in l
             and "Invalid condition id" not in l and "log4j" not in l
             and "Configure log4j" not in l]
    return proc.returncode, clean


if __name__ == "__main__":
    work = Path(sys.argv[1]).resolve()
    cmds = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    rc, out = run_mx(work, cmds)
    print("\n".join(out))
    print("rc =", rc)
