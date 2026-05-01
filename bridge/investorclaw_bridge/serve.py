# SPDX-License-Identifier: Apache-2.0
"""Entry point for the InvestorClaw v4.0 bridge.

Two listeners, one Python process:
  :8090  — MCP-HTTP server (FastMCP) — agent-facing tool surface
  :8092  — Dashboard web UI + REST + /healthz — user-facing config UI

Both ports share ic-engine session, sqlite db, and MnemosClient instance.

For the v4.0 beta pilot (24h timeline as of 2026-05-01):
  - MCP-HTTP at :8090 is load-bearing — at least 4 tools registered
    (portfolio_ask, portfolio_holdings, portfolio_refresh, portfolio_setup)
  - Dashboard at :8092 is minimal — placeholder static page + /healthz
  - mnemos-rs sibling container is OPTIONAL (not blocking for beta)
"""
from __future__ import annotations

import logging
import os
import sys

import structlog


def _configure_logging() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
    )


def _bind_addr_to_host_port(bind: str) -> tuple[str, int]:
    """Parse a bind string like '0.0.0.0:8090' into (host, port)."""
    if ":" not in bind:
        raise ValueError(f"Invalid bind address {bind!r} — expected HOST:PORT")
    host, port_str = bind.rsplit(":", 1)
    return host, int(port_str)


def main() -> int:
    """Start the bridge.

    Loads ic-engine bridge tooling + starts FastMCP at IC_MCP_BIND and
    a tiny FastAPI app at IC_DASHBOARD_BIND for /healthz + dashboard
    static files. Both run in the same uvicorn process via mounted
    sub-apps (one ASGI app at root, another mounted at /mcp).
    """
    _configure_logging()
    logger = structlog.get_logger("investorclaw_bridge.serve")

    # Defer heavy imports until after logging is configured (so import
    # errors get logged with structlog).
    try:
        from fastapi import FastAPI
        from fastapi.responses import JSONResponse
        from fastapi.staticfiles import StaticFiles
        import uvicorn
    except ImportError as e:
        logger.error("bridge.import_error", missing=str(e))
        sys.stderr.write(
            f"FATAL: missing required dependency: {e}. "
            f"Did you install via `pip install -e bridge/`?\n"
        )
        return 2

    try:
        # FastMCP — provides MCP-HTTP transport
        from mcp.server.fastmcp import FastMCP
    except ImportError:
        # FastMCP isn't packaged yet on all systems; for beta we can
        # serve a minimal /mcp endpoint manually if FastMCP is missing.
        FastMCP = None  # type: ignore[assignment]
        logger.warning(
            "bridge.fastmcp_missing",
            note="MCP server will be a placeholder; install `mcp` package for full functionality",
        )

    from . import mcp_server

    mcp_bind = os.environ.get("IC_MCP_BIND", "0.0.0.0:8090")
    dashboard_bind = os.environ.get("IC_DASHBOARD_BIND", "0.0.0.0:8092")
    mnemos_base = os.environ.get("MNEMOS_BASE", "http://mnemos:5002")

    logger.info(
        "bridge.start",
        mcp_bind=mcp_bind,
        dashboard_bind=dashboard_bind,
        mnemos_base=mnemos_base,
        ic_engine_db=os.environ.get("IC_ENGINE_DB", "/data/ic-engine.db"),
        portfolio_dir=os.environ.get("IC_PORTFOLIO_DIR", "/data/portfolios"),
    )

    # ── Build the dashboard FastAPI app ────────────────────────────────
    dashboard_app = FastAPI(title="InvestorClaw v4.0", version="4.0.0a1")

    @dashboard_app.get("/healthz")
    async def healthz() -> JSONResponse:
        return JSONResponse(mcp_server.health_check())

    @dashboard_app.get("/api/version")
    async def version() -> JSONResponse:
        return JSONResponse({"version": "4.0.0a1", "service": "investorclaw-bridge"})

    # Mount static dashboard files at /
    dashboard_dir = "/opt/ic-engine/dashboard"
    if os.path.isdir(dashboard_dir):
        dashboard_app.mount(
            "/", StaticFiles(directory=dashboard_dir, html=True), name="dashboard"
        )

    # ── Build the MCP-HTTP app ────────────────────────────────────────
    # FastMCP exposes its own ASGI app; we mount it at /mcp.
    if FastMCP is not None:
        mcp_app = FastMCP("investorclaw")
        mcp_server.register_tools(mcp_app)
        # FastMCP's HTTP transport: bind via streamable_http_app() if available
        # (depends on mcp package version — surface is in flux).
        try:
            mcp_asgi = mcp_app.streamable_http_app()
        except AttributeError:
            # Older mcp package — try sse_app() fallback
            try:
                mcp_asgi = mcp_app.sse_app()
            except AttributeError:
                logger.error(
                    "bridge.mcp_transport_unavailable",
                    note="FastMCP installed but no HTTP/SSE transport found; check mcp package version",
                )
                mcp_asgi = None
    else:
        mcp_asgi = None

    # Mount MCP at /mcp on the MCP-bound app (different port from dashboard)
    mcp_app_root = FastAPI(title="InvestorClaw MCP", version="4.0.0a1")

    @mcp_app_root.get("/healthz")
    async def mcp_healthz() -> JSONResponse:
        return JSONResponse(mcp_server.health_check())

    if mcp_asgi is not None:
        mcp_app_root.mount("/mcp", mcp_asgi, name="mcp")
    else:
        @mcp_app_root.get("/mcp")
        async def mcp_placeholder() -> JSONResponse:
            return JSONResponse(
                {
                    "error": "mcp_transport_unavailable",
                    "note": (
                        "FastMCP HTTP transport not initialized. "
                        "Install mcp>=1.4 or check ASGI integration."
                    ),
                },
                status_code=503,
            )

    # ── Run both listeners ─────────────────────────────────────────────
    # uvicorn can serve multiple ASGI apps via Config + Server multiplexing.
    # For simplicity in beta, we launch two uvicorn instances in asyncio.gather.
    import asyncio

    mcp_host, mcp_port = _bind_addr_to_host_port(mcp_bind)
    dash_host, dash_port = _bind_addr_to_host_port(dashboard_bind)

    mcp_config = uvicorn.Config(
        mcp_app_root, host=mcp_host, port=mcp_port, log_level="info"
    )
    dash_config = uvicorn.Config(
        dashboard_app, host=dash_host, port=dash_port, log_level="info"
    )
    mcp_uvicorn = uvicorn.Server(mcp_config)
    dash_uvicorn = uvicorn.Server(dash_config)

    async def _run_both() -> None:
        await asyncio.gather(mcp_uvicorn.serve(), dash_uvicorn.serve())

    try:
        asyncio.run(_run_both())
    except KeyboardInterrupt:
        logger.info("bridge.shutdown", reason="keyboard_interrupt")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
