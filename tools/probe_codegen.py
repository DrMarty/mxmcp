"""Standalone codegen smoke test."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from mxmcp.bundle import Pack
from mxmcp.standalone import DeviceDB, StandaloneProject
from mxmcp.codegen import Generator

out = Path("build/sacode")
p = StandaloneProject.load(DeviceDB(), "build/standalone/sa1.ioc")
print("project:", p.device.ref_name, "ips:", p.ips(), "pins:", len(p.pin_signals))
gen = Generator(p)
res = gen.generate(out, toolchain="Makefile", project_name="sa1")
print("files:", res["file_count"], res["files"])
main = (out / "Core" / "Src" / "main.c").read_text(encoding="utf-8")
print("--- main.c head ---")
print("\n".join(main.splitlines()[:40]))
print("--- param-derived lines ---")
for line in main.splitlines():
    if "from .ioc" in line:
        print(line)
