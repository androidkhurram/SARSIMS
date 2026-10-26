"""Stdio MCP client used by the web agent to call this project's tools."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import timedelta
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent.parent
PYTHON = ROOT / ".venv" / "bin" / "python"
SERVER = ROOT / "mcp_server.py"


def _python() -> str:
    if PYTHON.exists():
        return str(PYTHON)
    return sys.executable


def _string_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if isinstance(value, str) and not value.startswith("()")
    }
    if extra:
        env.update(extra)
    return env


async def _call_tool(
    name: str,
    arguments: dict,
    extra_env: dict[str, str] | None = None,
) -> dict:
    params = StdioServerParameters(
        command=_python(),
        args=[str(SERVER)],
        env=_string_env(extra_env),
        cwd=str(ROOT),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                name,
                arguments,
                read_timeout_seconds=timedelta(seconds=120),
            )

    text_parts = [
        block.text
        for block in result.content
        if getattr(block, "type", None) == "text" and getattr(block, "text", None)
    ]
    text = "\n".join(text_parts).strip()
    if result.isError:
        return {"error": text or "The MCP tool call failed."}
    if not text:
        return {"error": "The MCP tool returned an empty response."}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {"error": "The MCP tool returned invalid JSON.", "raw": text}
    if not isinstance(payload, dict):
        return {"error": "The MCP tool returned an unexpected payload."}
    payload["mcp_tool"] = name
    return payload


def call_mcp_tool(
    name: str,
    arguments: dict,
    extra_env: dict[str, str] | None = None,
) -> dict:
    """Call one MCP tool and return its JSON payload."""
    return asyncio.run(_call_tool(name, arguments, extra_env))
