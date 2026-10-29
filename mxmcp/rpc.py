"""Pure-python JSON-RPC 2.0 over stdio, MCP-shaped.

Implements exactly the subset of the Model Context Protocol an MCP client uses:

  initialize            -> protocolVersion, capabilities(tools), serverInfo
  notifications/initialized (no reply)
  tools/list            -> [{name, description, inputSchema}]
  tools/call            -> {content:[{type:text,text}], isError?}
  ping                  -> {}
  resources/list|read   -> optional static resources (docs, catalog index)
  prompts/list          -> empty

Framing: newline-delimited JSON, which is what the Python MCP SDK and
`mcp-cli`-style clients use over stdio. A `Content-Length` framed variant is
also accepted for robustness.

Everything is dependency free so the server can run on a stock python.exe.
"""
from __future__ import annotations

import json
import sys
import traceback
from typing import Any, Callable

PROTOCOL_VERSION = "2024-11-05"


class ToolError(Exception):
    """Raised by a tool to produce an isError result with a message."""


class McpServer:
    def __init__(self, name: str, version: str, instructions: str = "") -> None:
        self.name = name
        self.version = version
        self.instructions = instructions
        self.tools: dict[str, dict] = {}
        self.handlers: dict[str, Callable[[dict], Any]] = {}
        self.resources: dict[str, Callable[[], str]] = {}

    # ------------------------------------------------------------ registry
    def tool(self, name: str, description: str, schema: dict,
             handler: Callable[[dict], Any]) -> None:
        self.tools[name] = {"name": name, "description": description,
                            "inputSchema": schema}
        self.handlers[name] = handler

    def resource(self, uri: str, name: str, description: str,
                 loader: Callable[[], str]) -> None:
        self.resources[uri] = loader
        self._resource_meta = getattr(self, "_resource_meta", {})
        self._resource_meta[uri] = {"uri": uri, "name": name,
                                    "description": description,
                                    "mimeType": "text/plain"}

    # -------------------------------------------------------------- protocol
    def handle(self, msg: dict) -> dict | None:
        method = msg.get("method", "")
        msg_id = msg.get("id")
        params = msg.get("params") or {}
        if method in ("notifications/initialized", "notifications/cancelled",
                      "notifications/roots/list_changed"):
            return None
        try:
            if method == "initialize":
                result = {
                    "protocolVersion": params.get("protocolVersion", PROTOCOL_VERSION),
                    "capabilities": {
                        "tools": {"listChanged": False},
                        "resources": {"subscribe": False, "listChanged": False},
                    },
                    "serverInfo": {"name": self.name, "version": self.version},
                    **({"instructions": self.instructions} if self.instructions else {}),
                }
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": list(self.tools.values())}
            elif method == "tools/call":
                result = self._call_tool(params)
            elif method == "resources/list":
                result = {"resources": list(getattr(self, "_resource_meta", {}).values())}
            elif method == "resources/read":
                uri = params.get("uri", "")
                if uri not in self.resources:
                    raise ToolError(f"unknown resource {uri!r}")
                result = {"contents": [{"uri": uri, "mimeType": "text/plain",
                                        "text": self.resources[uri]()}]}
            elif method == "prompts/list":
                result = {"prompts": []}
            elif method == "logging/setLevel":
                result = {}
            else:
                raise ToolError(f"unknown method {method!r}")
            return {"jsonrpc": "2.0", "id": msg_id, "result": result}
        except ToolError as exc:
            if method == "tools/call":
                return {"jsonrpc": "2.0", "id": msg_id,
                        "result": {"content": [{"type": "text", "text": str(exc)}],
                                   "isError": True}}
            return {"jsonrpc": "2.0", "id": msg_id,
                    "error": {"code": -32602, "message": str(exc)}}
        except Exception as exc:  # noqa: BLE001
            tb = traceback.format_exc(limit=6)
            if method == "tools/call":
                return {"jsonrpc": "2.0", "id": msg_id,
                        "result": {"content": [{"type": "text",
                                                "text": f"{exc}\n{tb}"}],
                                   "isError": True}}
            return {"jsonrpc": "2.0", "id": msg_id,
                    "error": {"code": -32603, "message": f"{exc}\n{tb}"}}

    def _call_tool(self, params: dict) -> dict:
        name = params.get("name", "")
        args = params.get("arguments") or {}
        handler = self.handlers.get(name)
        if handler is None:
            raise ToolError(f"unknown tool {name!r}")
        out = handler(args)
        if isinstance(out, str):
            text = out
        else:
            text = json.dumps(out, indent=1, ensure_ascii=False)
        return {"content": [{"type": "text", "text": text}], "isError": False}

    # ----------------------------------------------------------------- loop
    def serve(self, stdin=None, stdout=None) -> None:
        stdin = stdin or sys.stdin.buffer
        stdout = stdout or sys.stdout.buffer
        while True:
            msg = self._read_message(stdin)
            if msg is None:
                break
            reply = self.handle(msg)
            if reply is not None:
                self._write_message(stdout, reply)

    @staticmethod
    def _read_message(stream) -> dict | None:
        line = stream.readline()
        if not line:
            return None
        stripped = line.strip()
        if not stripped:
            return None
        if stripped.lower().startswith(b"content-length:"):
            length = int(stripped.split(b":", 1)[1].strip())
            while True:
                hdr = stream.readline()
                if hdr in (b"\r\n", b"\n", b""):
                    break
            payload = stream.read(length)
        else:
            payload = stripped
        try:
            return json.loads(payload.decode("utf-8"))
        except json.JSONDecodeError:
            return {"jsonrpc": "2.0", "id": None, "method": "__bad_json__"}

    @staticmethod
    def _write_message(stream, msg: dict) -> None:
        data = json.dumps(msg, ensure_ascii=False).encode("utf-8")
        stream.write(data + b"\n")
        stream.flush()
