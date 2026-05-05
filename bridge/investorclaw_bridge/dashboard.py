# SPDX-License-Identifier: Apache-2.0
"""
InvestorClaw v4.x dashboard — server-rendered tabbed UI on :18092.

Each tab is its own FastAPI route returning a complete HTML page.
Section content reuses the engine's render helpers from
``ic_engine.rendering.eod_email_template`` so the dashboard tabs and the
EOD email render with identical styling and data shapes.

Tabs:
    /                     Overview — status + quick actions
    /dashboard/holdings   Top holdings + asset / sector breakdown
    /dashboard/performance Sharpe + Sortino + drawdown + period
    /dashboard/whatchanged Day-over-day attribution + top movers
    /dashboard/scenarios  Stress tests + drawdown / VaR
    /dashboard/bonds      Yield-to-maturity + duration + bond ladder
    /dashboard/analyst    Analyst consensus + price-target spread
    /dashboard/news       Per-holding headlines (with clickable links)
    /dashboard/synthesis  Multi-factor advisor narrative
    /dashboard/reports    Archive of generated EOD HTML reports
    /dashboard/settings   API-key management + provider config
    /dashboard/about      Version + license + disclaimer
"""
from __future__ import annotations

import datetime as _dt
import glob as _glob
import json as _json
import os
import pathlib
from typing import Any, Dict

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse


REPORTS_DIR = os.environ.get("IC_REPORTS_DIR", "/data/reports")

# (slug, label, icon)
TABS = [
    ("", "Overview", "📊"),
    ("holdings", "Holdings", "📁"),
    ("performance", "Performance", "📈"),
    ("whatchanged", "What Changed", "Δ"),
    ("scenarios", "Scenarios", "⚡"),
    ("bonds", "Bonds", "🏛"),
    ("analyst", "Analyst", "🎯"),
    ("news", "News", "📰"),
    ("synthesis", "Synthesis", "✦"),
    ("reports", "Reports", "📄"),
    ("settings", "Settings", "⚙"),
    ("about", "About", "ℹ"),
]


def _try_engine_helpers():
    """Import the engine's render helpers; return a stub set if unavailable."""
    try:
        from ic_engine.rendering import eod_email_template as t
        return t
    except ImportError:
        return None


_T = _try_engine_helpers()


def _load_json(filename: str) -> Dict[str, Any]:
    path = pathlib.Path(REPORTS_DIR) / filename
    if not path.is_file():
        return {}
    try:
        return _json.loads(path.read_text())
    except Exception:
        return {}


def _shell(active_slug: str, body: str, title: str = "InvestorClaw") -> str:
    """Wrap content in the standard dashboard shell with tab navigation."""
    nav_items = []
    for slug, label, icon in TABS:
        href = "/" if slug == "" else f"/dashboard/{slug}"
        active_cls = " active" if slug == active_slug else ""
        nav_items.append(
            f'<a href="{href}" class="tab{active_cls}">'
            f'<span class="tab-icon">{icon}</span>{label}</a>'
        )
    nav = "".join(nav_items)
    today = _dt.date.today().isoformat()
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} — InvestorClaw</title>
<style>
:root {{ color-scheme: dark light; }}
* {{ box-sizing: border-box; }}
body {{
  font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  margin: 0; padding: 0;
  background: #0d1117; color: #c9d1d9;
}}
@media (prefers-color-scheme: light) {{
  body {{ background: #fafbfc; color: #24292f; }}
}}
header {{
  background: #161b22; border-bottom: 1px solid #30363d;
  padding: 16px 32px; display: flex; justify-content: space-between; align-items: center;
}}
header h1 {{ font-size: 18px; margin: 0; color: #f0f6fc; }}
header .meta {{ color: #8b949e; font-size: 12px; }}
nav {{
  background: #161b22; border-bottom: 1px solid #30363d;
  padding: 0 16px; overflow-x: auto; white-space: nowrap;
}}
.tab {{
  display: inline-block; padding: 12px 16px; color: #8b949e;
  text-decoration: none; border-bottom: 3px solid transparent;
  transition: color 0.1s, border-color 0.1s;
}}
.tab:hover {{ color: #c9d1d9; }}
.tab.active {{ color: #58a6ff; border-bottom-color: #58a6ff; }}
.tab-icon {{ margin-right: 6px; opacity: 0.85; }}
main {{ padding: 24px 32px; max-width: 1200px; margin: 0 auto; }}
h2 {{ margin: 0 0 16px; font-size: 18px; color: #f0f6fc; }}
.muted {{ color: #8b949e; font-size: 13px; }}
a {{ color: #58a6ff; text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
a.primary {{
  display: inline-block; background: #238636; color: #fff;
  padding: 8px 14px; border-radius: 6px; font-weight: 600;
  margin: 4px 0;
}}
a.primary:hover {{ background: #2ea043; text-decoration: none; }}
code {{
  background: #161b22; padding: 2px 6px; border-radius: 3px;
  font-size: 12px; color: #c9d1d9;
}}
ul {{ list-style: none; padding: 0; margin: 0; }}
li {{ padding: 6px 0; border-bottom: 1px solid #21262d; }}
li:last-child {{ border-bottom: none; }}
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
.kpi-positive {{ color: #3fb950; }}
.kpi-negative {{ color: #f85149; }}
.empty {{
  background: #161b22; border: 1px dashed #30363d; border-radius: 6px;
  padding: 24px; text-align: center; color: #8b949e;
}}
.section-card {{
  background: #161b22; border: 1px solid #30363d; border-radius: 8px;
  padding: 16px; margin-bottom: 16px;
}}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
th {{
  text-align: left; padding: 8px 12px; background: #21262d;
  color: #c9d1d9; font-size: 11px; text-transform: uppercase;
  letter-spacing: 0.04em; font-weight: 600;
}}
td {{ padding: 6px 12px; border-bottom: 1px solid #21262d; }}
form .row {{ margin-bottom: 12px; }}
form label {{ display: block; color: #8b949e; font-size: 12px; margin-bottom: 4px; }}
form input[type="text"], form input[type="password"] {{
  background: #0d1117; border: 1px solid #30363d; border-radius: 4px;
  padding: 8px 12px; color: #c9d1d9; width: 360px; font-size: 13px;
}}
form button {{
  background: #238636; color: #fff; border: 0; padding: 8px 14px;
  border-radius: 6px; font-weight: 600; cursor: pointer;
}}
form button:hover {{ background: #2ea043; }}
.footer {{ margin-top: 48px; color: #8b949e; font-size: 12px; padding: 16px 0; border-top: 1px solid #21262d; }}
</style>
</head>
<body>

<header>
  <h1>InvestorClaw</h1>
  <span class="meta">{today} · v4.1.x</span>
</header>

<nav>{nav}</nav>

<main>
{body}
</main>

<div class="footer" style="padding-left:32px;padding-right:32px;max-width:1200px;margin:0 auto;">
  Educational only — not investment advice ·
  <a href="https://github.com/argonautsystems/InvestorClaw">project home</a> ·
  <a href="https://github.com/mnemos-os/mnemos-ic-runtime">runtime</a>
</div>

</body>
</html>"""


def _section_or_empty(rendered: str, empty_msg: str) -> str:
    """Return rendered HTML or an empty-state placeholder."""
    if rendered and rendered.strip():
        return rendered
    return f'<div class="empty">{empty_msg}</div>'


def _list_recent_eod_reports(limit: int = 30) -> list:
    """Return list of (filename, size_kb, mtime_iso) for recent EOD HTML files."""
    if not os.path.isdir(REPORTS_DIR):
        return []
    out = []
    for path in sorted(
        _glob.glob(os.path.join(REPORTS_DIR, "eod_report_*.html")), reverse=True
    )[:limit]:
        fname = os.path.basename(path)
        size_kb = os.path.getsize(path) / 1024
        mtime = _dt.datetime.fromtimestamp(os.path.getmtime(path)).strftime(
            "%Y-%m-%d %H:%M"
        )
        out.append((fname, size_kb, mtime))
    return out


# ----------------------------------------------------------------------------
# Per-tab handlers
# ----------------------------------------------------------------------------


def _overview(get_init_state) -> str:
    snap = get_init_state()
    today = _dt.date.today().isoformat()
    today_compact = today.replace("-", "")
    eod_today_path = os.path.join(REPORTS_DIR, f"eod_report_{today_compact}.html")
    has_today = os.path.isfile(eod_today_path)

    holdings = _load_json("holdings_summary.json")
    total_value = float((holdings.get("data") or holdings).get("total_value", 0) or 0)

    today_card = (
        f'<a href="/reports/eod_report_{today_compact}.html" class="primary">'
        f'Open today\'s EOD report ({today})</a>'
        if has_today
        else f'<p class="muted">No EOD report for {today} yet.</p>'
    )

    recent = _list_recent_eod_reports(7)
    recent_html = (
        "<ul>"
        + "\n".join(
            f'<li><a href="/reports/{fname}">{fname}</a> '
            f'<span class="muted">— {kb:.0f} KB · {mtime}</span></li>'
            for fname, kb, mtime in recent
        )
        + "</ul>"
        if recent
        else '<p class="muted">No reports generated yet. Run the pipeline.</p>'
    )

    body = f"""
<h2>Status</h2>
<div class="kpi-grid">
  <div class="kpi"><div class="kpi-label">Engine</div><div class="kpi-value">{snap['state']}</div></div>
  <div class="kpi"><div class="kpi-label">Init ready</div><div class="kpi-value">{'yes' if snap['ready'] else 'no'}</div></div>
  <div class="kpi"><div class="kpi-label">Total Value</div><div class="kpi-value">${total_value:,.0f}</div></div>
  <div class="kpi"><div class="kpi-label">MCP endpoint</div><div class="kpi-value"><code>:18090/mcp</code></div></div>
</div>

<h2>Today's EOD report</h2>
{today_card}

<h2>Recent EOD reports</h2>
{recent_html}

<h2>Quick links</h2>
<ul>
  <li><a href="/reports/">Browse all reports</a></li>
  <li><a href="/healthz">/healthz</a> · liveness JSON</li>
  <li><a href="/api/version">/api/version</a> · bridge version</li>
</ul>
"""
    return _shell("", body, title="Overview")


def _holdings_tab() -> str:
    holdings = _load_json("holdings_summary.json")
    analyst = _load_json("analyst_recommendations_summary.json")
    if not holdings:
        body = '<h2>Holdings</h2><div class="empty">No holdings data yet. Drop a portfolio file into <code>./portfolios/</code> and run <code>investorclaw setup</code>.</div>'
        return _shell("holdings", body, title="Holdings")
    parts = []
    if _T:
        parts.append(_T._render_portfolio_summary(holdings))
        parts.append(_T._render_top_holdings(holdings, analyst))
    else:
        parts.append('<div class="empty">Engine render helpers unavailable.</div>')
    body = "<h2>Holdings</h2>\n" + "\n".join(p for p in parts if p)
    return _shell("holdings", body, title="Holdings")


def _performance_tab() -> str:
    perf = _load_json("performance.json")
    if not perf:
        body = '<h2>Performance</h2><div class="empty">No performance data. Run <code>investorclaw performance</code> in the container.</div>'
    elif _T:
        body = "<h2>Performance</h2>\n" + _T._render_performance_summary(perf)
    else:
        body = "<h2>Performance</h2>\n" + _section_or_empty("", "Engine helpers unavailable.")
    return _shell("performance", body, title="Performance")


def _whatchanged_tab() -> str:
    wc = _load_json("whatchanged.json")
    if _T:
        body = "<h2>What Changed</h2>\n" + _section_or_empty(
            _T._render_whatchanged(wc),
            "No attribution data. Run <code>investorclaw whatchanged</code> in the container.",
        )
    else:
        body = "<h2>What Changed</h2>\n" + _section_or_empty("", "Engine helpers unavailable.")
    return _shell("whatchanged", body, title="What Changed")


def _scenarios_tab() -> str:
    scen = _load_json("scenario.json")
    if _T:
        body = "<h2>Scenarios &amp; Stress Tests</h2>\n" + _section_or_empty(
            _T._render_scenario(scen),
            "No scenario data. Run <code>investorclaw scenario</code> in the container.",
        )
    else:
        body = "<h2>Scenarios</h2>\n" + _section_or_empty("", "Engine helpers unavailable.")
    return _shell("scenarios", body, title="Scenarios")


def _bonds_tab() -> str:
    bonds = _load_json("bond_analysis.json")
    if _T:
        body = "<h2>Fixed Income</h2>\n" + _section_or_empty(
            _T._render_bond_summary(bonds),
            "No bond data (your portfolio may have no bond holdings, or run <code>investorclaw bonds</code>).",
        )
    else:
        body = "<h2>Fixed Income</h2>\n" + _section_or_empty("", "Engine helpers unavailable.")
    return _shell("bonds", body, title="Bonds")


def _analyst_tab() -> str:
    a = _load_json("analyst_recommendations_summary.json")
    if _T:
        body = "<h2>Analyst Coverage</h2>\n" + _section_or_empty(
            _T._render_analyst_summary(a),
            "No analyst data. Run <code>investorclaw analyst</code>.",
        )
    else:
        body = "<h2>Analyst</h2>\n" + _section_or_empty("", "Engine helpers unavailable.")
    return _shell("analyst", body, title="Analyst")


def _news_tab() -> str:
    n = _load_json("portfolio_news.json")
    if _T:
        body = "<h2>News</h2>\n" + _section_or_empty(
            _T._render_news_summary(n),
            "No news data. Run <code>investorclaw news</code> in the container.",
        )
    else:
        body = "<h2>News</h2>\n" + _section_or_empty("", "Engine helpers unavailable.")
    return _shell("news", body, title="News")


def _synthesis_tab() -> str:
    syn = _load_json("portfolio_analysis.json")
    if not syn:
        body = '<h2>Synthesis</h2><div class="empty">No synthesis data. Run <code>investorclaw synthesize</code>.</div>'
        return _shell("synthesis", body, title="Synthesis")

    # synthesis is a dict; render the narrative and any FA topics
    narr = (syn.get("data") or syn).get("narrative") or syn.get("narrative") or ""
    parts = ["<h2>Synthesis</h2>"]
    if narr:
        narr_html = "<br>".join(line.strip() for line in narr.splitlines() if line.strip())
        parts.append(f'<div class="section-card">{narr_html}</div>')
    # FA topics
    if _T:
        try:
            from ic_engine.commands.fa_discussion import extract_fa_topics
            topics = extract_fa_topics(pathlib.Path(REPORTS_DIR), preloaded={"synthesize": syn})
            parts.append(_section_or_empty(_T._render_fa_topics(topics), ""))
        except Exception:
            pass
    body = "\n".join(parts)
    return _shell("synthesis", body, title="Synthesis")


def _reports_tab() -> str:
    reports = _list_recent_eod_reports(50)
    if not reports:
        body = '<h2>Reports</h2><div class="empty">No EOD reports generated yet.</div>'
    else:
        rows = []
        for fname, kb, mtime in reports:
            rows.append(
                f'<tr><td><a href="/reports/{fname}">{fname}</a></td>'
                f'<td>{kb:.0f} KB</td><td class="muted">{mtime}</td></tr>'
            )
        table = (
            "<table><tr><th>Report</th><th>Size</th><th>Generated</th></tr>"
            + "".join(rows)
            + "</table>"
        )
        body = f"""<h2>Reports archive</h2>
<p class="muted">{len(reports)} EOD reports on disk. Click a row to view in this browser, or download the HTML.</p>
<div class="section-card">{table}</div>
<h2>JSON snapshots</h2>
<p class="muted">Raw section data behind the dashboard tabs.</p>
<ul>"""
        json_files = sorted(_glob.glob(os.path.join(REPORTS_DIR, "*.json")))
        for jp in json_files:
            jname = os.path.basename(jp)
            jsize = os.path.getsize(jp) / 1024
            body += f'<li><a href="/reports/{jname}">{jname}</a> <span class="muted">— {jsize:.1f} KB</span></li>'
        body += "</ul>"
    return _shell("reports", body, title="Reports")


def _settings_tab(get_keys_status, message: str = "") -> str:
    status = get_keys_status()
    configured = status.get("configured", []) or []
    settable = status.get("settable", []) or []
    msg_html = (
        f'<div class="section-card" style="border-color:#3fb950;color:#3fb950;">{message}</div>'
        if message
        else ""
    )

    config_rows = []
    for key in configured:
        config_rows.append(
            f"<tr><td><code>{key}</code></td>"
            "<td><span class=\"kpi-positive\">configured</span></td></tr>"
        )
    for key in settable:
        if key not in configured:
            config_rows.append(
                f"<tr><td><code>{key}</code></td>"
                "<td class=\"muted\">not set</td></tr>"
            )

    set_form = """<form action="/dashboard/settings/keys" method="post">
  <div class="row">
    <label>Key name</label>
    <input type="text" name="key_name" placeholder="TOGETHER_API_KEY" required>
  </div>
  <div class="row">
    <label>Value (saved to /data/keys.env mode 0600 inside the container)</label>
    <input type="password" name="key_value" placeholder="tgp_v1_..." required>
  </div>
  <button type="submit">Save key</button>
</form>"""

    body = f"""<h2>Settings — provider keys</h2>
{msg_html}
<p class="muted">Keys persist to <code>/data/keys.env</code> inside the named Docker volume,
mode 0600. Allowlisted names only — arbitrary key names are rejected.</p>

<div class="section-card">
  <table>
    <tr><th>Key</th><th>Status</th></tr>
    {"".join(config_rows)}
  </table>
</div>

<h2>Add or update a key</h2>
<div class="section-card">
{set_form}
</div>
"""
    return _shell("settings", body, title="Settings")


def _about_tab() -> str:
    body = """<h2>About InvestorClaw</h2>
<div class="section-card">
  <p><strong>InvestorClaw v4.1.x</strong> — deterministic-first portfolio analyzer.</p>
  <p>Real money math, no LLM math. Holdings, performance (Sharpe + Sortino, max drawdown,
  beta, value-at-risk), bond duration, FRED yield curves, sector breakdowns, scenario
  rebalancing. The engine is pure Python; the narrator is an LLM with strict
  no-fabrication validation against an HMAC-signed envelope.</p>
</div>

<h2>License</h2>
<div class="section-card">
  <p>Substantive code (bridge, dashboard, Dockerfile, tests): <strong>Apache 2.0</strong>.</p>
  <p>Distribution-edge artifacts (SKILL.md, compose.yml, install.yaml, agent-skills/**):
  <strong>MIT-0</strong> (MIT No Attribution).</p>
</div>

<h2>Repos</h2>
<ul>
  <li><a href="https://github.com/argonautsystems/InvestorClaw">argonautsystems/InvestorClaw</a> — umbrella project (this repo)</li>
  <li><a href="https://github.com/mnemos-os/mnemos-ic-runtime">mnemos-os/mnemos-ic-runtime</a> — v4.x dockerized-skill runtime</li>
  <li><a href="https://github.com/argonautsystems/ic-engine">argonautsystems/ic-engine</a> — Python engine source</li>
  <li><a href="https://github.com/argonautsystems/InvestorClaude">argonautsystems/InvestorClaude</a> — v2.6.x Claude Code marketplace plugin</li>
</ul>

<h2>Disclaimer</h2>
<div class="section-card" style="border-color:#d29922;color:#e3b341;">
  <p><strong>Educational analysis only — NOT investment advice.</strong></p>
  <p>InvestorClaw is not a fiduciary advisor and does not execute trades, move money,
  or authenticate to brokerage accounts. Always consult a qualified financial advisor
  before acting on any analysis output.</p>
</div>
"""
    return _shell("about", body, title="About")


# ----------------------------------------------------------------------------
# FastAPI wiring
# ----------------------------------------------------------------------------


def attach_to(app: FastAPI, get_init_state, get_keys_status, set_key) -> None:
    """Mount all dashboard tab routes on the given FastAPI app.

    Parameters
    ----------
    get_init_state : callable -> dict
        Returns the engine init snapshot (state, ready, current_stage, elapsed_ms).
    get_keys_status : callable -> dict
        Returns ``{"configured": [...], "settable": [...]}``.
    set_key : callable(name, value) -> dict
        Persists a single key, returns ``{"configured": [...], "rejected": [...]}``.
    """

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def overview() -> HTMLResponse:
        return HTMLResponse(_overview(get_init_state))

    @app.get("/dashboard/", include_in_schema=False)
    async def dashboard_root() -> RedirectResponse:
        return RedirectResponse(url="/", status_code=303)

    @app.get("/dashboard/holdings", response_class=HTMLResponse, include_in_schema=False)
    async def holdings() -> HTMLResponse:
        return HTMLResponse(_holdings_tab())

    @app.get("/dashboard/performance", response_class=HTMLResponse, include_in_schema=False)
    async def performance() -> HTMLResponse:
        return HTMLResponse(_performance_tab())

    @app.get("/dashboard/whatchanged", response_class=HTMLResponse, include_in_schema=False)
    async def whatchanged() -> HTMLResponse:
        return HTMLResponse(_whatchanged_tab())

    @app.get("/dashboard/scenarios", response_class=HTMLResponse, include_in_schema=False)
    async def scenarios() -> HTMLResponse:
        return HTMLResponse(_scenarios_tab())

    @app.get("/dashboard/bonds", response_class=HTMLResponse, include_in_schema=False)
    async def bonds() -> HTMLResponse:
        return HTMLResponse(_bonds_tab())

    @app.get("/dashboard/analyst", response_class=HTMLResponse, include_in_schema=False)
    async def analyst() -> HTMLResponse:
        return HTMLResponse(_analyst_tab())

    @app.get("/dashboard/news", response_class=HTMLResponse, include_in_schema=False)
    async def news() -> HTMLResponse:
        return HTMLResponse(_news_tab())

    @app.get("/dashboard/synthesis", response_class=HTMLResponse, include_in_schema=False)
    async def synthesis() -> HTMLResponse:
        return HTMLResponse(_synthesis_tab())

    @app.get("/dashboard/reports", response_class=HTMLResponse, include_in_schema=False)
    async def reports() -> HTMLResponse:
        return HTMLResponse(_reports_tab())

    @app.get("/dashboard/settings", response_class=HTMLResponse, include_in_schema=False)
    async def settings(message: str = "") -> HTMLResponse:
        # get_keys_status may be sync or async (e.g. portfolio_keys_status is async)
        import inspect as _inspect
        result = get_keys_status()
        if _inspect.iscoroutine(result):
            result = await result
        return HTMLResponse(_settings_tab(lambda: result, message=message))

    @app.post("/dashboard/settings/keys", include_in_schema=False)
    async def settings_save_key(request: Request) -> RedirectResponse:
        form = await request.form()
        name = (form.get("key_name") or "").strip()
        value = (form.get("key_value") or "").strip()
        if not name or not value:
            return RedirectResponse(
                url="/dashboard/settings?message=Missing+name+or+value",
                status_code=303,
            )
        import inspect as _inspect
        result = set_key(name, value)
        if _inspect.iscoroutine(result):
            result = await result
        rejected = result.get("rejected") or []
        if rejected:
            msg = f"Key {name} rejected (not in allowlist)"
        else:
            msg = f"Saved {name}"
        from urllib.parse import quote
        return RedirectResponse(
            url=f"/dashboard/settings?message={quote(msg)}",
            status_code=303,
        )

    @app.get("/dashboard/about", response_class=HTMLResponse, include_in_schema=False)
    async def about() -> HTMLResponse:
        return HTMLResponse(_about_tab())
