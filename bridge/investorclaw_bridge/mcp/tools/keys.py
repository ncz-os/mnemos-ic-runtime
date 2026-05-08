# SPDX-License-Identifier: Apache-2.0
"""Key-management tools — agent-driven API key configuration.

Lets an agent (zeroclaw / openclaw / hermes / claude-desktop) prompt the
user for an API key and POST it directly to the container, instead of
requiring host shell access to edit `/data/keys.env`.

Designed so an MD-skill-only agent install path can configure keys via
either MCP (`portfolio_keys_set`) or plain REST (`POST /api/portfolio/keys/set`).

Persistence: writes to `/data/keys.env` mode 0600 via `setup_api._save_keys`,
which makes the keys survive container restart (the `/data` volume is
bind-mounted per compose.yml).

Liveness: also pushes the new keys into `os.environ` so subprocesses
spawned by the bridge after the call (i.e. the next portfolio_ask) inherit
them. No bridge restart required.

Allowlist: only KNOWN_KEYS may be set via this surface. This prevents an
agent from setting arbitrary container env vars that could affect engine
behavior. Adding a new settable key requires updating the KNOWN_KEYS
catalogue in setup_api.py and rebuilding the image.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .. import _runtime  # for logger
from .._runtime import logger
from ...key_resolver import KeysFileTooPermissiveError, load_keys_env


_ALLOWLIST: set[str] | None = None


def _allowlist() -> set[str]:
    """Return the set of settable key names. Reuses setup_api.KNOWN_KEYS."""
    global _ALLOWLIST
    if _ALLOWLIST is None:
        try:
            from investorclaw_bridge.setup_api import KNOWN_KEYS
            _ALLOWLIST = {k["name"] for k in KNOWN_KEYS}
        except Exception:
            # Conservative fallback if setup_api isn't importable —
            # the canonical six keys per compose.yml's optional_keys.
            _ALLOWLIST = {
                "TOGETHER_API_KEY",
                "OPENAI_API_KEY",
                "FINNHUB_KEY",
                "FRED_API_KEY",
                "NEWSAPI_KEY",
                "ALPHA_VANTAGE_KEY",
                "MASSIVE_API_KEY",
                "MARKETAUX_API_KEY",
            }
    return _ALLOWLIST


def _read_existing() -> dict[str, str]:
    """Read existing keys, refusing overly permissive keys.env files."""
    keys_file = Path(os.environ.get("IC_KEYS_FILE", "/data/keys.env"))
    try:
        return load_keys_env(keys_file)
    except KeysFileTooPermissiveError as exc:
        logger.warning(
            "mcp.keys_file_too_permissive",
            path=str(keys_file),
            error=str(exc),
        )
        return {}
    except OSError:
        return {}


def _persist(updates: dict[str, str]) -> None:
    """Persist via setup_api (which writes mode 0600, sorts, dedupes)."""
    from investorclaw_bridge.setup_api import _save_keys
    _save_keys(updates)


def _push_into_environ(updates: dict[str, str]) -> None:
    """Mirror the keys into the bridge's os.environ so subprocesses pick
    them up immediately. Only sets keys with a non-empty value; empty
    values are deletions (also reflected here).
    """
    for name, value in updates.items():
        if value:
            os.environ[name] = value
        else:
            os.environ.pop(name, None)


# ──────────────────────────────────────────────────────────────────────
# Pure tool handlers (transport-agnostic)
# ──────────────────────────────────────────────────────────────────────


async def portfolio_keys_status() -> dict[str, Any]:
    """Return which keys are currently configured (NOT their values)."""
    existing = _read_existing()
    allowlist = _allowlist()
    return {
        "configured": sorted(k for k in allowlist if existing.get(k)),
        "settable": sorted(allowlist),
        "missing": sorted(k for k in allowlist if not existing.get(k)),
        "keys_file": os.environ.get("IC_KEYS_FILE", "/data/keys.env"),
    }


async def portfolio_keys_set(keys: dict[str, str]) -> dict[str, Any]:
    """Set one or more API keys.

    Args:
        keys: mapping of KEY_NAME → value. Names not in the allowlist are
            rejected with a 400-shaped response. Empty/None values delete
            the key.

    Returns:
        {"configured": [...], "rejected": [...], "deleted": [...]}.
    """
    if not isinstance(keys, dict) or not keys:
        return {
            "error": "missing_keys",
            "detail": "Provide a non-empty mapping of KEY_NAME -> value.",
            "configured": [],
            "rejected": [],
            "deleted": [],
        }

    allowlist = _allowlist()
    rejected = sorted(k for k in keys if k not in allowlist)
    if rejected:
        return {
            "error": "rejected_keys_not_in_allowlist",
            "detail": (
                "These names are not settable via this surface. "
                "See `settable` field of /api/portfolio/keys/status."
            ),
            "configured": [],
            "rejected": rejected,
            "deleted": [],
            "settable": sorted(allowlist),
        }

    # Normalize values
    updates = {
        name: ((value or "").strip() if isinstance(value, str) else "")
        for name, value in keys.items()
    }

    # Persist + mirror into environ
    _persist(updates)
    _push_into_environ(updates)

    set_keys = sorted(k for k, v in updates.items() if v)
    deleted_keys = sorted(k for k, v in updates.items() if not v)
    logger.info(
        "mcp.keys.set",
        configured=set_keys,
        deleted=deleted_keys,
    )
    return {
        "configured": set_keys,
        "rejected": [],
        "deleted": deleted_keys,
    }


# ──────────────────────────────────────────────────────────────────────
# Size-aware key recommendation (#44) — surface "you should set
# MASSIVE_API_KEY at this portfolio size" guidance to the agent / dashboard
# so users with large portfolios aren't surprised by yfinance throttling.
# ──────────────────────────────────────────────────────────────────────

# Threshold above which yfinance free-tier throttling becomes a real
# problem (rate-limits at ~50 symbols, blocks at ~100 in a single batch).
# Bumping these triggers a STRONG recommend for MASSIVE_API_KEY.
_LARGE_PORTFOLIO_THRESHOLD = 50    # >50 holdings → strong-recommend
_HUGE_PORTFOLIO_THRESHOLD = 100    # >100 → strong-recommend everywhere


def _count_portfolio_holdings(portfolio_path: str) -> int | None:
    """Count rows in a portfolio CSV (excluding header).

    Returns None if the file doesn't exist or can't be parsed. Falls back
    to None on any read error rather than raising — this is advisory data
    for the recommend endpoint, not a hard requirement.
    """
    from pathlib import Path
    p = Path(portfolio_path)
    if not p.exists():
        return None
    try:
        # Try multiple encodings — same posture as portfolio_sizer.
        for enc in ("utf-8-sig", "utf-8", "latin-1"):
            try:
                with p.open("r", encoding=enc, newline="") as f:
                    import csv
                    reader = csv.DictReader(f)
                    return sum(1 for _ in reader)
            except UnicodeDecodeError:
                continue
        return None
    except Exception:
        return None


def _active_portfolio_path() -> str | None:
    """Return the active portfolio CSV path under /data/portfolios.

    Picks the most-recently-modified file, matching auto_setup's pick-the-
    only-portfolio convention. Returns None if the directory is empty or
    unreadable.
    """
    from pathlib import Path
    portfolio_dir = Path(os.environ.get("IC_PORTFOLIO_DIR", "/data/portfolios"))
    if not portfolio_dir.is_dir():
        return None
    candidates = [p for p in portfolio_dir.glob("*.csv") if p.is_file()]
    if not candidates:
        return None
    # Most-recently-modified wins — matches auto_setup behavior.
    return str(max(candidates, key=lambda p: p.stat().st_mtime))


def _key_recommendations(holdings_count: int | None) -> dict[str, Any]:
    """Build a structured recommendation block for the agent / dashboard.

    Each key entry has:
        priority — "required" | "strongly_recommended" | "recommended" | "optional"
        reason   — human-readable why this priority for THIS portfolio size

    The narrator endpoint (TOGETHER_API_KEY) is `strongly_recommended`
    universally — without it, ic-engine falls back to the heuristic
    narrator which produces catalog-style answers, not narrative ones.
    """
    recs: list[dict[str, Any]] = []

    # Narrator — always strongly recommended.
    recs.append({
        "name": "TOGETHER_API_KEY",
        "priority": "strongly_recommended",
        "reason": (
            "Narrator endpoint. Without it, ic-engine falls back to the "
            "heuristic narrator (envelope-catalog style); LLM-driven "
            "narrative answers are unavailable. Free tier sufficient for "
            "most users."
        ),
        "signup_url": "https://api.together.xyz/",
    })

    # Massive — priority scales with size.
    if holdings_count is not None and holdings_count >= _HUGE_PORTFOLIO_THRESHOLD:
        massive_priority = "strongly_recommended"
        massive_reason = (
            f"Portfolio has {holdings_count} holdings (>={_HUGE_PORTFOLIO_THRESHOLD}). "
            "yfinance free-tier rate-limits and times out at this size. "
            "MASSIVE_API_KEY (Polygon) provides parallelized batch fetching "
            "without throttling — without it, refresh will be slow and "
            "incomplete."
        )
    elif holdings_count is not None and holdings_count >= _LARGE_PORTFOLIO_THRESHOLD:
        massive_priority = "recommended"
        massive_reason = (
            f"Portfolio has {holdings_count} holdings "
            f"(>={_LARGE_PORTFOLIO_THRESHOLD}). yfinance throttling becomes "
            "noticeable; MASSIVE_API_KEY parallelizes the price fetch and "
            "avoids the slow path."
        )
    else:
        size_note = (
            f"Portfolio has {holdings_count} holdings"
            if holdings_count is not None
            else "Portfolio size unknown"
        )
        massive_priority = "optional"
        massive_reason = (
            f"{size_note}. yfinance free-tier is fine at this size; "
            "MASSIVE_API_KEY only needed for large portfolios "
            f"(>={_LARGE_PORTFOLIO_THRESHOLD} holdings)."
        )

    recs.append({
        "name": "MASSIVE_API_KEY",
        "priority": massive_priority,
        "reason": massive_reason,
        "signup_url": "https://polygon.io/",
    })

    # News providers — recommended (any one, two-source for coverage).
    for name, signup, blurb in [
        ("FINNHUB_KEY", "https://finnhub.io/",
         "Earnings, analyst ratings, company-specific news"),
        ("MARKETAUX_API_KEY", "https://www.marketaux.com/",
         "Equity-tagged news with sentiment scoring"),
        ("NEWSAPI_KEY", "https://newsapi.org/",
         "Broad news API, supplements Finnhub for non-listed coverage"),
        ("ALPHA_VANTAGE_KEY", "https://www.alphavantage.co/",
         "Fundamentals + corporate actions"),
    ]:
        recs.append({
            "name": name,
            "priority": "recommended",
            "reason": blurb,
            "signup_url": signup,
        })

    # FRED — optional (macro context).
    recs.append({
        "name": "FRED_API_KEY",
        "priority": "optional",
        "reason": "Macro / treasury yield context. Free, no rate limit.",
        "signup_url": "https://fred.stlouisfed.org/docs/api/api_key.html",
    })

    return {"keys": recs}


async def portfolio_keys_recommend(portfolio_path: str | None = None) -> dict[str, Any]:
    """Return size-aware API key recommendations for the active portfolio.

    Inspects the portfolio (default: most-recently-modified CSV under
    /data/portfolios) and returns a per-key priority + rationale block:

      - Portfolios with >=100 holdings: MASSIVE_API_KEY → strongly_recommended
      - Portfolios with >=50 holdings: MASSIVE_API_KEY → recommended
      - Smaller portfolios: MASSIVE_API_KEY → optional

    TOGETHER_API_KEY is always strongly_recommended (narrator endpoint).
    News + FRED keys carry their normal priority.

    Use case: dashboard Settings tab + agent setup-orchestrator surface
    the recommendation so users with 200-holding portfolios know upfront
    that they need a Polygon key for non-throttled refresh.
    """
    path = portfolio_path or _active_portfolio_path()
    holdings_count = _count_portfolio_holdings(path) if path else None
    existing = _read_existing()
    block = _key_recommendations(holdings_count)
    # Annotate each recommendation with its current configured state.
    for entry in block["keys"]:
        entry["configured"] = bool(existing.get(entry["name"]))
    return {
        "portfolio_path": path,
        "holdings_count": holdings_count,
        "recommendations": block["keys"],
    }


async def portfolio_keys_delete(name: str) -> dict[str, Any]:
    """Delete a single configured key by name."""
    if name not in _allowlist():
        return {
            "error": "rejected_key_not_in_allowlist",
            "detail": "Name not settable via this surface.",
            "deleted": False,
            "settable": sorted(_allowlist()),
        }
    _persist({name: ""})
    _push_into_environ({name: ""})
    logger.info("mcp.keys.delete", name=name)
    return {"deleted": True, "name": name}


# ──────────────────────────────────────────────────────────────────────
# Tool descriptors (registered via TOOL_REGISTRY in tools/__init__.py)
# ──────────────────────────────────────────────────────────────────────


def _tool(description: str, parameters: dict, required: list[str], handler) -> dict:
    return {
        "description": description,
        "parameters": parameters,
        "required": required,
        "handler": handler,
    }


KEYS_TOOLS: dict[str, dict[str, Any]] = {
    "portfolio_keys_status": _tool(
        description=(
            "Report which API keys are currently configured for ic-engine. "
            "Returns names only — never key values. Use this to check what's "
            "set before prompting the user for a missing key."
        ),
        parameters={},
        required=[],
        handler=portfolio_keys_status,
    ),
    "portfolio_keys_set": _tool(
        description=(
            "Set one or more ic-engine API keys. Persisted to /data/keys.env "
            "(mode 0600) and immediately available to the next portfolio_ask "
            "call without restart. Only the standard ic-engine keys are "
            "settable: TOGETHER_API_KEY, OPENAI_API_KEY, FINNHUB_KEY, "
            "FRED_API_KEY, NEWSAPI_KEY, ALPHA_VANTAGE_KEY. Other names are "
            "rejected. Empty values delete the key."
        ),
        parameters={
            "keys": {
                "type": "object",
                "description": (
                    "Mapping of KEY_NAME (str) -> value (str). Only allowlisted "
                    "names accepted. Empty value deletes the key."
                ),
            },
        },
        required=["keys"],
        handler=portfolio_keys_set,
    ),
    "portfolio_keys_delete": _tool(
        description=(
            "Delete a single configured ic-engine API key by name. Only "
            "allowlisted names accepted."
        ),
        parameters={
            "name": {
                "type": "string",
                "description": "Key name to delete (must be in the allowlist).",
            },
        },
        required=["name"],
        handler=portfolio_keys_delete,
    ),
    "portfolio_keys_recommend": _tool(
        description=(
            "Return size-aware API key recommendations for the active "
            "portfolio. Inspects the most-recently-modified CSV under "
            "/data/portfolios (or `portfolio_path` if provided) and "
            "returns per-key priority (`strongly_recommended` / "
            "`recommended` / `optional`) + rationale + signup_url + "
            "current configured state. Use this to surface portfolio-"
            "specific guidance to the user — large portfolios get "
            "MASSIVE_API_KEY upgraded to strongly_recommended because "
            "yfinance throttles. TOGETHER_API_KEY is always strongly_"
            "recommended (narrator endpoint)."
        ),
        parameters={
            "portfolio_path": {
                "type": "string",
                "description": (
                    "Optional explicit portfolio CSV path. If omitted, "
                    "the most-recently-modified CSV under /data/portfolios "
                    "is used."
                ),
            },
        },
        required=[],
        handler=portfolio_keys_recommend,
    ),
}
