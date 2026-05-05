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
        from fastapi.responses import HTMLResponse, JSONResponse
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

    # Load /data/keys.env into os.environ so ic-engine subprocesses inherit
    # the keys (FINNHUB_KEY, MASSIVE_API_KEY, ALPHA_VANTAGE_KEY, NEWSAPI_KEY,
    # TOGETHER/INVESTORCLAW_NARRATIVE_API_KEY, etc.). The key_resolver module
    # parses + validates mode 0600; we only set keys not already in env so
    # operator-set ENV (Dockerfile / compose) wins over file values.
    from pathlib import Path
    from . import key_resolver

    keys_path = Path(os.environ.get("IC_KEYS_FILE", "/data/keys.env"))
    try:
        loaded = key_resolver.load_keys_env(keys_path)
        added = 0
        for k, v in loaded.items():
            if k not in os.environ:
                os.environ[k] = v
                added += 1
        logger.info(
            "bridge.keys.loaded",
            path=str(keys_path),
            in_file=len(loaded),
            added_to_env=added,
            keys=sorted(loaded.keys()),
        )
    except Exception as e:
        logger.warning(
            "bridge.keys.load_failed",
            path=str(keys_path),
            error=f"{type(e).__name__}: {e}",
        )

    mcp_bind = os.environ.get("IC_MCP_BIND", "0.0.0.0:8090")
    dashboard_bind = os.environ.get("IC_DASHBOARD_BIND", "0.0.0.0:8092")
    mnemos_base = os.environ.get("MNEMOS_BASE", "http://mnemos:5002")

    logger.info(
        "bridge.start",
        mcp_bind=mcp_bind,
        dashboard_bind=dashboard_bind,
        mnemos_base=mnemos_base,
        portfolio_dir=os.environ.get("IC_PORTFOLIO_DIR", "/data/portfolios"),
        engine_portfolio_dir=os.environ.get("INVESTOR_CLAW_PORTFOLIO_DIR", "(unset)"),
    )

    # ── Build the dashboard FastAPI app ────────────────────────────────
    dashboard_app = FastAPI(title="InvestorClaw v4.0", version="4.0.0a1")

    @dashboard_app.get("/healthz")
    async def healthz() -> JSONResponse:
        # Health includes init state so agents polling /healthz can also
        # gate on `init_state == "ready"` without an extra round-trip.
        from .mcp.tools import get_init_state as _get_init_state
        h = mcp_server.health_check()
        snap = _get_init_state()
        h["init_state"] = snap["state"]
        h["init_ready"] = snap["ready"]
        h["init_current_stage"] = snap["current_stage"]
        h["init_elapsed_ms"] = snap["elapsed_ms"]
        return JSONResponse(h)

    @dashboard_app.get("/api/version")
    async def version() -> JSONResponse:
        return JSONResponse({"version": "4.0.0a1", "service": "investorclaw-bridge"})

    # Wire the first-run setup API + bare-metal HTML form
    # (per GRAEAE 2026-05-01 — keep pilots in browser, out of nano)
    from . import setup_api
    setup_api.attach_to(dashboard_app)

    # Mount static dashboard files at /static (root is taken by setup redirect)
    dashboard_dir = "/opt/ic-engine/dashboard"
    if os.path.isdir(dashboard_dir):
        dashboard_app.mount(
            "/static", StaticFiles(directory=dashboard_dir, html=True), name="dashboard"
        )

    # Mount /reports → /data/reports so users can browse generated EOD HTML
    # files, JSON snapshots, etc. directly via http://localhost:18092/reports/
    # The reports dir is the bind-mounted ./reports/ on the host.
    reports_dir = os.environ.get("IC_REPORTS_DIR", "/data/reports")
    if os.path.isdir(reports_dir):
        dashboard_app.mount(
            "/reports",
            StaticFiles(directory=reports_dir, html=True),
            name="reports",
        )

    # Landing page at / — lists today's EOD report (if any), portfolio status,
    # and links into the reports archive. Replaces the prior 405 Method Not
    # Allowed at GET /.
    @dashboard_app.get("/", response_class=HTMLResponse)
    async def dashboard_landing() -> HTMLResponse:
        from .mcp.tools import get_init_state as _get_init_state
        import datetime as _dt
        import glob as _glob

        snap = _get_init_state()
        today = _dt.date.today().isoformat()
        eod_today_html = f"/reports/eod_report_{today.replace('-', '')}.html"
        eod_today_path = os.path.join(reports_dir, f"eod_report_{today.replace('-', '')}.html")
        has_today_eod = os.path.isfile(eod_today_path)

        # Recent EOD reports (newest first)
        recent_html = []
        if os.path.isdir(reports_dir):
            for path in sorted(
                _glob.glob(os.path.join(reports_dir, "eod_report_*.html")),
                reverse=True,
            )[:14]:
                fname = os.path.basename(path)
                size_kb = os.path.getsize(path) / 1024
                mtime = _dt.datetime.fromtimestamp(os.path.getmtime(path)).strftime(
                    "%Y-%m-%d %H:%M"
                )
                recent_html.append(
                    f'<li><a href="/reports/{fname}">{fname}</a> '
                    f'<span class="muted">— {size_kb:.0f} KB · {mtime}</span></li>'
                )

        recent_block = (
            "<ul>" + "\n".join(recent_html) + "</ul>"
            if recent_html
            else '<p class="muted">No EOD reports generated yet. '
            'Run <code>investorclaw eod-report --run</code> in the container.</p>'
        )

        today_card = (
            f'<a href="{eod_today_html}" class="primary">Open today\'s EOD report ({today})</a>'
            if has_today_eod
            else f'<p class="muted">No EOD report for {today} yet.</p>'
        )

        body = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>InvestorClaw — Dashboard</title>
<style>
:root {{ color-scheme: dark light; }}
body {{
  font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  margin: 0; padding: 32px; max-width: 880px;
  background: #0d1117; color: #c9d1d9;
}}
@media (prefers-color-scheme: light) {{
  body {{ background: #fafbfc; color: #24292f; }}
}}
h1 {{ margin: 0 0 4px; font-size: 28px; }}
h2 {{ margin: 32px 0 12px; font-size: 18px; border-bottom: 1px solid #30363d; padding-bottom: 6px; }}
.muted {{ color: #8b949e; font-size: 13px; }}
a {{ color: #58a6ff; text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
a.primary {{
  display: inline-block; background: #238636; color: #fff;
  padding: 10px 18px; border-radius: 6px; font-weight: 600;
  margin: 8px 0;
}}
a.primary:hover {{ background: #2ea043; text-decoration: none; }}
code {{
  background: #161b22; padding: 2px 6px; border-radius: 3px;
  font-size: 12px; color: #c9d1d9;
}}
ul {{ list-style: none; padding: 0; }}
li {{ padding: 6px 0; border-bottom: 1px solid #21262d; }}
.kpi-grid {{
  display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px; margin: 12px 0;
}}
.kpi {{
  background: #161b22; border: 1px solid #30363d; border-radius: 6px;
  padding: 14px;
}}
.kpi-label {{ color: #8b949e; font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em; }}
.kpi-value {{ color: #c9d1d9; font-size: 18px; font-weight: 600; margin-top: 4px; }}
.footer {{ margin-top: 48px; color: #8b949e; font-size: 12px; }}
</style>
</head>
<body>

<h1>InvestorClaw</h1>
<p class="muted">Deterministic-first portfolio analysis · Educational use only</p>

<h2>Status</h2>
<div class="kpi-grid">
  <div class="kpi"><div class="kpi-label">Engine</div><div class="kpi-value">{snap['state']}</div></div>
  <div class="kpi"><div class="kpi-label">Init ready</div><div class="kpi-value">{'yes' if snap['ready'] else 'no'}</div></div>
  <div class="kpi"><div class="kpi-label">MCP endpoint</div><div class="kpi-value"><code>:18090/mcp</code></div></div>
  <div class="kpi"><div class="kpi-label">REST</div><div class="kpi-value"><code>:18090/api/portfolio/</code></div></div>
</div>

<h2>Today's EOD report</h2>
{today_card}

<h2>Recent EOD reports</h2>
{recent_block}

<h2>API</h2>
<ul>
  <li><a href="/healthz">/healthz</a> <span class="muted">— liveness + init state JSON</span></li>
  <li><a href="/api/version">/api/version</a> <span class="muted">— bridge version JSON</span></li>
  <li><a href="/reports/">/reports/</a> <span class="muted">— browse reports directory (HTML + JSON snapshots)</span></li>
  <li><code>POST /api/portfolio/ask</code> <span class="muted">— natural-language portfolio query</span></li>
  <li><code>POST /api/portfolio/holdings</code> <span class="muted">— holdings snapshot</span></li>
  <li><code>POST /api/portfolio/refresh</code> <span class="muted">— force fresh data pull</span></li>
  <li><code>POST /api/portfolio/keys_set</code> <span class="muted">— configure provider keys</span></li>
</ul>

<div class="footer">
  InvestorClaw v4.x · <a href="https://github.com/mnemos-os/mnemos-ic-runtime">GitHub</a>
  · <a href="https://github.com/argonautsystems/InvestorClaw">Project home</a>
  · Educational only — not investment advice.
</div>

</body>
</html>"""
        return HTMLResponse(content=body)

    # ── Build the MCP-HTTP app ────────────────────────────────────────
    # FastMCP exposes its own ASGI app via streamable_http_app(), but the
    # session manager inside it must be started via an async context
    # manager (`session_manager.run()`) — wired through FastAPI's lifespan
    # parameter. Mounting without the lifespan gives:
    #   RuntimeError: Task group is not initialized. Make sure to use run().
    # See FastMCP docs for the canonical lifespan-mount pattern.
    from contextlib import asynccontextmanager

    if FastMCP is not None:
        # MCP server's StreamableHTTP transport ships DNS-rebinding protection
        # (mcp.server.transport_security.TransportSecuritySettings, on by
        # default). With allowed_hosts=[] and protection on, every Host header
        # except 127.0.0.1/localhost is rejected. That breaks the v4.0
        # container-to-container path: an agent in a sibling container hits the
        # bridge over the docker bridge IP (172.17.0.1:18090 in default bridge
        # mode, or `<service-name>:8090` in compose's user-defined bridge) and
        # gets `Streamable HTTP error: Invalid Host header`.
        #
        # The convention (RFC §8) is localhost-only by default, but localhost
        # is the *host*, not the *container*'s view of the host. For the
        # in-cluster MCP path to work at all, we need to allow the container
        # bridge IPs and compose service names.
        #
        # Default: disable rebinding protection (this service is meant to be
        # reached by sibling containers + localhost; not exposed publicly).
        # Override via env: MCP_ALLOWED_HOSTS=host1,host2,... to keep
        # protection on with an explicit allowlist.
        from mcp.server.transport_security import TransportSecuritySettings
        _allowed_hosts = os.environ.get("MCP_ALLOWED_HOSTS", "").strip()
        if _allowed_hosts:
            _sec = TransportSecuritySettings(
                enable_dns_rebinding_protection=True,
                allowed_hosts=[h.strip() for h in _allowed_hosts.split(",") if h.strip()],
            )
        else:
            _sec = TransportSecuritySettings(enable_dns_rebinding_protection=False)
        mcp_app = FastMCP("investorclaw", transport_security=_sec)
        mcp_server.register_tools(mcp_app)
        try:
            mcp_asgi = mcp_app.streamable_http_app()
        except AttributeError:
            try:
                mcp_asgi = mcp_app.sse_app()
            except AttributeError:
                logger.error(
                    "bridge.mcp_transport_unavailable",
                    note="FastMCP installed but no HTTP/SSE transport found; check mcp package version",
                )
                mcp_app = None
                mcp_asgi = None
    else:
        mcp_app = None
        mcp_asgi = None

    @asynccontextmanager
    async def mcp_lifespan(app):
        if mcp_app is not None and hasattr(mcp_app, "session_manager"):
            async with mcp_app.session_manager.run():
                yield
        else:
            yield

    # MCP-bound FastAPI app — mounts FastMCP at root so the inner /mcp path
    # becomes /mcp on the agent's URL. /healthz lives at root alongside.
    mcp_app_root = FastAPI(
        title="InvestorClaw MCP",
        version="4.0.0a1",
        lifespan=mcp_lifespan,
    )

    @mcp_app_root.get("/healthz")
    async def mcp_healthz() -> JSONResponse:
        from .mcp.tools import get_init_state as _get_init_state
        h = mcp_server.health_check()
        snap = _get_init_state()
        h["init_state"] = snap["state"]
        h["init_ready"] = snap["ready"]
        h["init_current_stage"] = snap["current_stage"]
        h["init_elapsed_ms"] = snap["elapsed_ms"]
        return JSONResponse(h)

    # Register REST wrappers BEFORE the FastMCP mount; FastAPI route
    # resolution prefers explicitly-registered routes over mounted apps,
    # so /api/portfolio/* takes precedence over the FastMCP catch-all.
    mcp_server.register_rest_routes(mcp_app_root)

    if mcp_asgi is not None:
        # Mount at root: FastMCP's internal /mcp path becomes the public /mcp.
        # This is the canonical path agents expect (see RFC §6.2 transport=http).
        mcp_app_root.mount("/", mcp_asgi)
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

    # Boot-time auto-initialize so by the time any agent connects, the
    # envelope cache is already warm. The agent gets sub-second responses
    # on its very first portfolio_ask instead of the 5–15min cold-cache
    # path. Disable with IC_INITIALIZE_ON_BOOT=0.
    initialize_on_boot = os.environ.get("IC_INITIALIZE_ON_BOOT", "1").strip() not in ("0", "false", "no", "")

    async def _auto_initialize() -> None:
        # Brief delay so the listeners are up before we spawn engine subprocesses.
        await asyncio.sleep(2.0)
        try:
            from .mcp.tools.portfolio import portfolio_initialize
            logger.info("bridge.auto_initialize.start")
            result = await portfolio_initialize(seed_question="What is in my portfolio?")
            logger.info(
                "bridge.auto_initialize.done",
                ready=result.get("ready"),
                total_duration_ms=result.get("total_duration_ms"),
                stages=[s.get("stage") + ":" + str(s.get("exit_code")) for s in result.get("stages", [])],
            )
        except Exception as e:
            logger.warning("bridge.auto_initialize.failed", error=f"{type(e).__name__}: {e}")

    async def _run_both() -> None:
        tasks = [mcp_uvicorn.serve(), dash_uvicorn.serve()]
        if initialize_on_boot:
            tasks.append(_auto_initialize())
        await asyncio.gather(*tasks)

    try:
        asyncio.run(_run_both())
    except KeyboardInterrupt:
        logger.info("bridge.shutdown", reason="keyboard_interrupt")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
