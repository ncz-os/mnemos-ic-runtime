<!--
SPDX-License-Identifier: MIT
Copyright 2026 InvestorClaw Contributors

This SKILL.md is MIT-licensed. The InvestorClaw service it connects to is
Apache 2.0. See LICENSE-MIT in this directory.
-->

# InvestorClaw — Skill

> Powered by [InvestorClaw](https://investorclaw.app) (Apache 2.0).
> This skill file is MIT-licensed; the underlying service is Apache 2.0.

## What this is

InvestorClaw is a containerized portfolio analysis service that exposes
its analytical capabilities via two MCP-HTTP servers:

- `investorclaw` (port 8090) — portfolio analysis tools (holdings,
  performance, bonds, news, optimization, etc.)
- `mnemos` (port 5002) — memory + knowledge graph (remember user
  preferences, prior observations, conversation context)

The user is the orchestrator. The service is the substrate. Your agent
runtime is the interface. **Your job: connect to the MCP servers, call
the tools, interpret the structured results.**

## Tool surface (v4.0.0a1 beta)

> ⚠️ **v4.0.0a1 ships with 4 portfolio tools.** Additional tools land in
> v4.0.0a2+. **Do not call** any tool name not in this list — they are
> not wired yet, and calling them produces a tool-not-found error that
> wastes the user's turn. **Route everything through `portfolio_ask`** —
> it dispatches to the right analyzer behind the scenes and is the
> stable surface for all portfolio questions.

### Portfolio analysis (`investorclaw_*`)

Beta-pilot tool surface — 4 tools, all snake_case (no dots, satisfies
upstream OpenAI / MCP tool-name validation):

- **`investorclaw_portfolio_ask`** — natural-language portfolio question
  routed through the deterministic engine. **Use this for everything.**
  The engine routes to the right internal analyzer (holdings,
  performance, bonds, news, optimization, etc.) based on the question.
- **`investorclaw_portfolio_holdings`** — current snapshot of positions /
  values / weights / account hierarchy.
- **`investorclaw_portfolio_refresh`** — re-fetch market data without
  re-uploading portfolio files. Pulls fresh prices via yfinance / FRED /
  Finnhub (depending on which keys are configured).
- **`investorclaw_portfolio_setup`** — auto-discover portfolio files in
  `/data/portfolios/`. Use on first run, or after the user uploads a new
  portfolio file via the dashboard.

### NOT in v4.0.0a1 — defer to portfolio_ask

The following capabilities ARE in the deterministic engine, but are
NOT exposed as separate tools yet — `portfolio_ask` is the access path:

- Performance analytics (Sharpe, volatility, drawdown) — ask "how is
  my portfolio performing?"
- Bond analytics (YTM, duration, FRED yield curve) — ask "what does
  my bond portfolio look like?"
- News correlation — ask "what's in the news about my holdings?"
- Optimization (Sharpe, min-vol) — ask "what's an optimized weighting?"
- Analyst ratings, peer comparison, scenarios, cashflow, lookup,
  guardrails — all routable via `portfolio_ask`.

Specific tool wrappers for these will land in v4.0.0a2 once the beta
pilot signal validates the architecture.

### Memory (deferred for beta)

The mnemos-rs companion container is **not shipped in v4.0.0a1 beta**.
Memory tools (`mnemos.search_memories`, `mnemos.create_memory`,
`mnemos.list_memories`) will appear once the mnemos-rs sibling container
lands in v4.0.0a2+. For beta: portfolio analysis is stateless across
turns; the agent's own conversation memory is the only persistence.

## How to use it

1. **For portfolio questions:** call `investorclaw.portfolio_ask` with the
   user's natural-language question. The deterministic engine routes it
   to the right analyzer and returns a structured `ic_result` envelope
   plus a narrative text body. **Trust the structured output** — it's
   deterministic. **Decorate the narrative** if the user wants more
   context.

2. **For follow-up questions:** call `mnemos.search_memories` first to
   pull relevant prior observations (e.g., user's risk tolerance, prior
   discussions about specific holdings). Then call the appropriate
   `investorclaw.*` tool with that context in mind.

3. **For "what changed" questions:** call `mnemos.search_memories` for
   prior portfolio summaries; the LLM can compare against the current
   `investorclaw.portfolio_holdings` output.

4. **After delivering an analysis:** call `mnemos.create_memory` to
   record any salient observations the user might want to remember
   (e.g., "User flagged BABA as a never-sell sentimental position
   during the 2026-04-30 review"). Don't over-record — only what's
   non-obvious from re-reading the data.

## Important behaviors

- **The investorclaw tools are deterministic at the data layer.** If a
  format isn't recognized, you'll get a structured error with detected
  columns and supported formats. Don't ask the LLM to disambiguate —
  surface the error to the user and direct them to the dashboard's
  column-mapping wizard at http://localhost:8092/portfolios/map.

- **Educational only — never investment advice.** All outputs include
  the disclaimer envelope. Echo it when summarizing for the user.

- **The MCP server runs locally by default.** It's at
  http://127.0.0.1:8090/mcp and http://127.0.0.1:5002/mcp. If the user
  deploys remotely (Tailscale VM, cloud), the URLs change but the tool
  surface is identical.

## How to install (if not yet running)

If `investorclaw.*` tools aren't responding, the service isn't running.
You can install it:

1. Verify Docker is available: `docker --version` (or Podman)
2. Stage the compose file:
   ```
   mkdir -p ~/.investorclaw
   curl -sSL https://get.investorclaw.app/v4.0/compose.yml > ~/.investorclaw/compose.yml
   ```
3. Start the service:
   ```
   cd ~/.investorclaw && docker compose up -d
   ```
4. Wait for health: poll `http://127.0.0.1:8090/healthz` until 200.
5. Add the MCP servers to your config (instructions vary per agent
   runtime; see `install.yaml` for ordered steps per agent).
6. Reload config / restart your agent so it picks up the new MCP
   servers.
7. Open the dashboard at http://127.0.0.1:8092/ to upload the user's
   portfolio file.

For zeroclaw on master: a single command does all of the above:

```
zeroclaw services install https://get.investorclaw.app/v4.0/compose.yml
```

(zeroclaw `services` subcommand is in upstream PR — check master
availability before assuming it's there.)

## Connection settings

Your MCP server config should have:

```json
{
  "mcpServers": {
    "investorclaw": {
      "transport": "http",
      "url": "http://127.0.0.1:8090/mcp"
    },
    "mnemos": {
      "transport": "http",
      "url": "http://127.0.0.1:5002/mcp"
    }
  }
}
```

(zeroclaw uses TOML; openclaw uses `mcp.servers` block; hermes uses YAML
`mcp_servers:`. The dashboard's "Connect an agent" wizard generates the
right format per detected agent.)

## What this skill does NOT do

- Does not manage money or execute trades
- Does not give investment advice
- Does not access user accounts or move funds
- Educational outputs only

## Reporting issues

This skill describes the InvestorClaw service. If a tool returns an
unexpected result, the issue is in the service (Apache 2.0,
`perlowja/InvestorClaw` + `mnemos-os/mnemos-ic-runtime`), not in this
SKILL.md.
