"""Smoke test for the standalone engine (no CubeMX, no JVM)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from mxmcp.bundle import Pack
from mxmcp.ipmodes import IPModes
from mxmcp.standalone import DeviceDB, StandaloneProject, StandaloneError

out = Path("build/standalone")
out.mkdir(parents=True, exist_ok=True)

db = DeviceDB()
print("pack available:", db.available, "mcus:", len(db.names()))
print("resolve STM32F103C8T6 ->", db.resolve("STM32F103C8T6")[:2])

p = StandaloneProject.create(db, "STM32F103C8T6", pid="sa1")
dev = p.device
print("device:", dev.ref_name, dev.family, dev.package, "pins:", len(dev.pins),
      "ips:", len(dev.ips))

print("PA9 signals:", [s for s in p.available_signals("PA9")][:8])
print("pins for USART1_TX:", dev.pins_for_signal("USART1_TX"))

print(p.set_pin("PA9", "USART1_TX"))
print(p.set_pin("PA10", "USART1_RX"))
print(p.set_pin("PC13", "GPIO_Output"))
try:
    p.set_pin("PA9", "USART3_TX")
except StandaloneError as exc:
    print("rejected as expected:", str(exc)[:90])

print(p.set_mode("USART1", "Asynchronous"))
p.set_ip_param("USART1", "BaudRate", "115200")
print(p.set_nvic("USART1_IRQn", priority=1, enabled=True))

im = IPModes(db.pack)
print("FREERTOS modes:", im.modes("FREERTOS"))
print("USART params:", [x["name"] for x in im.parameters("USART1")][:8])

path = p.save(out / "sa1.ioc")
print("saved:", path, path.stat().st_size, "bytes")
print("problems:", p.problems())

# reload round-trip
q = StandaloneProject.load(db, path)
print("reloaded:", q.device.ref_name, "pins:", q.pin_signals,
      "ips:", q.ips())
print("round-trip identical:",
      q.to_ioc().dumps() == p.to_ioc().dumps())
