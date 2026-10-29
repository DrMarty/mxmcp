"""Schem helpers for tool definitions (kept tiny and explicit)."""
from __future__ import annotations


def obj(props: dict, required: list[str] | None = None, **extra) -> dict:
    return {"type": "object", "properties": props,
            "required": required or [], **extra}


def s(desc: str, enum: list[str] | None = None, default=None) -> dict:
    d = {"type": "string", "description": desc}
    if enum:
        d["enum"] = enum
    if default is not None:
        d["default"] = default
    return d


def i(desc: str, default=None, minimum=None, maximum=None) -> dict:
    d = {"type": "integer", "description": desc}
    if default is not None:
        d["default"] = default
    if minimum is not None:
        d["minimum"] = minimum
    if maximum is not None:
        d["maximum"] = maximum
    return d


def b(desc: str, default=None) -> dict:
    d = {"type": "boolean", "description": desc}
    if default is not None:
        d["default"] = default
    return d


def arr(desc: str, items: dict, default=None) -> dict:
    d = {"type": "array", "description": desc, "items": items}
    if default is not None:
        d["default"] = default
    return d


def anyobj(desc: str) -> dict:
    return {"type": "object", "description": desc, "additionalProperties": True}


def enum(values: list[str], desc: str, default=None) -> dict:
    d = {"type": "string", "description": desc, "enum": values}
    if default is not None:
        d["default"] = default
    return d


def n(desc: str, default=None) -> dict:
    d = {"type": "number", "description": desc}
    if default is not None:
        d["default"] = default
    return d
