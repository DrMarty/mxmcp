"""mxmcp - Model Context Protocol server for STM32CubeMX.

Two modes share one MCP surface:

* hybrid    - drives the official CubeMX command interpreter in a warm JVM, so pin
              legality, clock solving, code templates and generation behave exactly
              like the desktop application.
* standalone- needs no CubeMX installation: a bundled data pack (built locally with
              `python -m mxmcp.bundle build`) provides the MCU/IP/template model, and
              `standalone.py` + `codegen.py` implement validation and C generation.

Read-only lookups always prefer the shipped database or the bundled pack.
"""
from __future__ import annotations

__version__ = "1.1.0"
__all__ = ["__version__"]
