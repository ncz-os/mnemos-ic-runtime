# SPDX-License-Identifier: Apache-2.0
"""Transport adapters: FastMCP (MCP-HTTP) + FastAPI REST.

Both adapters iterate the canonical TOOL_REGISTRY in mcp/tools/__init__.py
and wire each tool to the appropriate decorator. Tool business logic lives
in tools/portfolio.py as pure async functions; this module is purely
transport plumbing.

The two transports are co-equal:
- MCP (FastMCP streamable_http) — primary, RFC-blessed.
- REST (FastAPI POST routes) — fallback for runtimes whose native MCP
  client integration has gaps. Added in v4.0.5; same backend, same
  ic_result envelope.

Future migration: when the MCP Python SDK's SSE transport
(mcp.server.sse.SseServerTransport) is preferred over FastMCP's
streamable_http_app(), only this module changes. tools/* and _runtime
stay put.
"""
from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel as _BaseModel

from . import _runtime
from ._runtime import logger
from .tools import TOOL_REGISTRY


# ──────────────────────────────────────────────────────────────────────
# MCP transport (FastMCP streamable-http)
# ──────────────────────────────────────────────────────────────────────


def register_tools(app: Any) -> None:
    """Register all tools in TOOL_REGISTRY on a FastMCP application.

    `app` is an mcp.server.fastmcp.FastMCP instance. The caller wires
    transport (HTTP at :8090) + auth.
    """

    @app.tool()
    async def portfolio_ask(question: str) -> dict[str, Any]:
        """Ask a natural-language portfolio question via ic-engine."""
        return await TOOL_REGISTRY["portfolio_ask"]["handler"](question)

    @app.tool()
    async def portfolio_holdings() -> dict[str, Any]:
        """Current portfolio holdings snapshot."""
        return await TOOL_REGISTRY["portfolio_holdings"]["handler"]()

    @app.tool()
    async def portfolio_refresh() -> dict[str, Any]:
        """Refresh market data without re-uploading portfolio files."""
        return await TOOL_REGISTRY["portfolio_refresh"]["handler"]()

    @app.tool()
    async def portfolio_setup() -> dict[str, Any]:
        """Auto-discover portfolio files in /data/portfolios/."""
        return await TOOL_REGISTRY["portfolio_setup"]["handler"]()

    @app.tool()
    async def portfolio_keys_status() -> dict[str, Any]:
        """Report which API keys are currently configured (names only)."""
        return await TOOL_REGISTRY["portfolio_keys_status"]["handler"]()

    @app.tool()
    async def portfolio_keys_set(keys: dict[str, str]) -> dict[str, Any]:
        """Set one or more API keys; persists to /data/keys.env (mode 0600)."""
        return await TOOL_REGISTRY["portfolio_keys_set"]["handler"](keys)

    @app.tool()
    async def portfolio_keys_delete(name: str) -> dict[str, Any]:
        """Delete a single configured API key by name."""
        return await TOOL_REGISTRY["portfolio_keys_delete"]["handler"](name)

    logger.info(
        "mcp.tools.registered",
        tools=list(TOOL_REGISTRY.keys()),
    )


# ──────────────────────────────────────────────────────────────────────
# REST transport (FastAPI POST routes — fallback for flaky MCP clients)
# ──────────────────────────────────────────────────────────────────────


# Pydantic body model for /api/portfolio/ask. Defined at module scope (NOT
# closure-local inside register_rest_routes) so FastAPIs Pydantic v2
# TypeAdapter can fully resolve the ForwardRef. A closure-local class hits
# PydanticUserError: '... is not fully defined' at first request.
class AskBody(_BaseModel):
    question: str


class KeysSetBody(_BaseModel):
    """Bulk-set body. Names must be in the allowlist (see /api/portfolio/keys/status)."""
    keys: dict[str, str]


class KeysDeleteBody(_BaseModel):
    """Single-name delete body."""
    name: str


def register_rest_routes(app: Any) -> None:
    """Register REST wrappers on a FastAPI app for the same tools as MCP.

    See module docstring. Bridge exposes /api/portfolio/{ask,holdings,
    refresh,setup,tools}; agents that have shell+curl can hit these
    without going through the MCP handshake.
    """
    from fastapi import HTTPException, Body

    @app.post("/api/portfolio/ask")
    async def rest_portfolio_ask(body: AskBody = Body(...)) -> dict[str, Any]:
        if not body.question:
            raise HTTPException(status_code=400, detail="question is required")
        return await TOOL_REGISTRY["portfolio_ask"]["handler"](body.question)

    @app.post("/api/portfolio/holdings")
    async def rest_portfolio_holdings() -> dict[str, Any]:
        return await TOOL_REGISTRY["portfolio_holdings"]["handler"]()

    @app.post("/api/portfolio/refresh")
    async def rest_portfolio_refresh() -> dict[str, Any]:
        return await TOOL_REGISTRY["portfolio_refresh"]["handler"]()

    @app.post("/api/portfolio/setup")
    async def rest_portfolio_setup() -> dict[str, Any]:
        return await TOOL_REGISTRY["portfolio_setup"]["handler"]()

    # Key management — paths match tool names exactly (`portfolio_keys_*`)
    # so agents can derive URLs from the catalog's `path` field directly.
    # POST for both status and set keeps the surface uniform with the
    # other portfolio_* tools (some MCP-bridged HTTP clients only emit
    # POST for tool-call style verbs).
    @app.post("/api/portfolio/keys_status")
    async def rest_keys_status() -> dict[str, Any]:
        """Which API keys are configured (names only). Safe — never returns values."""
        return await TOOL_REGISTRY["portfolio_keys_status"]["handler"]()

    @app.post("/api/portfolio/keys_set")
    async def rest_keys_set(body: KeysSetBody = Body(...)) -> dict[str, Any]:
        """Set or delete API keys (allowlisted only).

        Body shape: `{"keys": {"FINNHUB_KEY": "...", "TOGETHER_API_KEY": "..."}}`.
        Empty value deletes the key. Names not in the allowlist are rejected
        with a structured 200 response (NOT 400 — agents read the `rejected`
        field). Bridge mirrors keys into os.environ live, so the next
        portfolio_ask sees them without restart.
        """
        return await TOOL_REGISTRY["portfolio_keys_set"]["handler"](body.keys)

    @app.post("/api/portfolio/keys_delete")
    async def rest_keys_delete(body: KeysDeleteBody = Body(...)) -> dict[str, Any]:
        """Delete a single configured key by name. Allowlisted names only."""
        return await TOOL_REGISTRY["portfolio_keys_delete"]["handler"](body.name)

    # Convenience: a GET alias on /api/portfolio/keys/status for browser/dev
    # use. The canonical path remains /api/portfolio/keys_status to match
    # the tool name and catalog discovery.
    @app.get("/api/portfolio/keys/status")
    async def rest_keys_status_alias() -> dict[str, Any]:
        return await TOOL_REGISTRY["portfolio_keys_status"]["handler"]()

    @app.get("/api/portfolio/tools")
    async def rest_portfolio_tools() -> dict[str, Any]:
        """Self-describing tool catalog — agents can curl this to discover endpoints."""
        catalog = []
        for name, info in TOOL_REGISTRY.items():
            entry = {
                "name": name,
                "method": "POST",
                "path": f"/api/portfolio/{name.removeprefix('portfolio_')}",
                "body": (
                    {p: schema.get("type", "string") for p, schema in info["parameters"].items()}
                    if info["parameters"] else {}
                ),
                "description": info["description"],
            }
            catalog.append(entry)
        return {"tools": catalog}

    logger.info(
        "mcp.rest_routes.registered",
        endpoints=[f"/api/portfolio/{n.removeprefix('portfolio_')}" for n in TOOL_REGISTRY.keys()] + ["/api/portfolio/tools"],
    )
