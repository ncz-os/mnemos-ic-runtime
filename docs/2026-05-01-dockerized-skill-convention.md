# The dockerized skill: a stability layer for agentic code that survives runtime upgrades

**By Jason Perlow** · 2026-05-01 · Tags: agents, MCP, zeroclaw, openclaw, hermes, claude, architecture, RFC

---

> **TL;DR.** Agentic skills written in non-trivial code (Python, JS, native binaries) keep breaking every time their host agent runtime ships a new release. The fix isn't to chase each runtime's install conventions — it's to stop installing skills *into* agents at all. Run the skill in its own Docker container; let the agent talk to it via MCP. The agent's "skill file" collapses to a single Markdown document. The dependency arrow inverts: agents become clients of stable services, instead of skills being downstream of every runtime's install pain.
>
> This post tells the story, shows the architecture, and embeds the formal RFC for what I'm calling the **`compose-x-mcp-services` convention**. I'm shipping the first reference implementation (InvestorClaw v4.0) and proposing zeroclaw as the reference *installer* (`zeroclaw services install <compose-url>`). Comments welcome.

---

## The eight-hour day that made the architecture obvious

I've been building [InvestorClaw](https://investorclaw.app) for a few months — a deterministic portfolio analyzer that does real money math: Sharpe ratios, FRED yield curves, bond duration, sector breakdowns, scenario rebalancing, the whole works. About 60 Python files on top of `pandas`, `numpy`, `scipy`, `polars`, `openpyxl`, plus the FINOS CDM 5.x data model. Around 200 MB of resident scientific stack.

I wanted it to work everywhere. So I built install paths for the four major agent runtimes:

- **Claude Code** (Anthropic's marketplace plugin)
- **openclaw** (Node-based; gateway + MCP + plugins)
- **zeroclaw** (Rust; lean, MCP-native on master)
- **hermes** (Python; NousResearch; tool-rich)

And I tested them. Hard. Thirty real cobol-ish portfolio prompts, N=3 trials, on Linux first and then on a fresh Windows-WSL Docker setup as a stress test for the worst-case install environment.

Here's what I found on **2026-04-28** (Linux v2.5.0 baseline):

| Runtime | Score |
|---|---|
| Claude Code | 30/30 (100%) |
| openclaw | 26/30 (86%) |
| hermes | 23/30 (76%) |
| zeroclaw | not run (auth gate at the time) |

Decent. Not perfect, but decent. Then I spent the next two days iterating — `ic-engine` v2.6.1 (cold-cache fix), v2.6.2 (`uv` over `pip` on PEP 668), v2.6.3 (audit-compliant skill bundle, openclaw 4.29-beta.4 schema fixes). I rewrote installer scripts, updated plugin manifests, added bootstrap-workspace seeding. And on **2026-04-30**, with all of those fixes in place, on TYPHON Windows-WSL Docker:

| Runtime | Score | Status |
|---|---|---|
| openclaw 4.29-beta.4 | 21/30 (70%) | regression vs Linux 86% |
| zeroclaw 0.7.x demo | 6/30 (20%) | broken: PATH + auth + tool-name validation |
| hermes 0.12 | 6/30 (20%) | regression vs Linux 76% |

Eight hours of debugging that day. Every regression was install friction. Not analytical bugs in the engine — the engine code is mathematically sound. The failures were in the *seam* between the skill and the runtime: openclaw 4.29-beta.4 added a config-health daemon that detected my JSON writes as "suspicious" and reverted them; zeroclaw 0.7.3 had skill-audit rules different from what I'd been targeting; hermes treats skills as documentation hints injected into the system prompt rather than first-class function-callable tools, so empirical reliability there is structurally capped.

Each issue was a real bug. Each fix was real and locally correct. **The pattern that emerged from the day was bigger than any individual fix:** I was permanently downstream of N agent runtimes × M release cadences. A 60-file deterministic portfolio engine — code that calculates *real money* — was broken by upstream churn in JavaScript plugin loaders and Rust autonomy gates and Python skill-discovery semantics. None of which had anything to do with portfolios.

If I keep playing this game, I lose. The half-life of any given install path is measured in weeks. Claude Code is the only one with stable enough plugin conventions to not hurt — and that's because it's Anthropic's stack, treated as a first-class product surface. The other three are *agent runtimes evolving fast*, which is the right thing for them to be doing. They shouldn't slow down for me.

So I asked: what if my skill stops trying to live inside their runtime?

---

## The pivot: skills as services, not bundles

Here's the architectural inversion in one diagram:

### Before (v2.x — the broken model)

```
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  zeroclaw       │  │  openclaw       │  │  hermes         │  │  claude code    │
│  agent          │  │  agent          │  │  agent          │  │  agent          │
│                 │  │                 │  │                 │  │                 │
│  ┌───────────┐  │  │  ┌───────────┐  │  │  ┌───────────┐  │  │  ┌───────────┐  │
│  │ skill #1  │  │  │  │ skill #1  │  │  │  │ skill #1  │  │  │  │ plugin #1 │  │
│  │ ─ Python  │  │  │  │ ─ Python  │  │  │  │ ─ Python  │  │  │  │ ─ Python  │  │
│  │ ─ deps    │  │  │  │ ─ deps    │  │  │  │ ─ deps    │  │  │  │ ─ deps    │  │
│  │ ─ uv venv │  │  │  │ ─ uv venv │  │  │  │ ─ uv venv │  │  │  │ ─ uv venv │  │
│  └───────────┘  │  │  └───────────┘  │  │  └───────────┘  │  │  └───────────┘  │
└─────────────────┘  └─────────────────┘  └─────────────────┘  └─────────────────┘

Four installs. Four different package managers. Four different audit rules. 
Four different ways the agent runtime invokes the skill's CLI verbs. 
Each runtime's release cycle breaks the install in a new way.
The skill author chases breakage forever.
```

### After (v4.0 — the dockerized-skill convention)

```
                ┌──────────────────────────────────────┐
                │     skill-as-service container       │
                │     (Apache 2.0 service code)        │
                │                                      │
                │     Python venv + deps + skill code  │
                │                                      │
                │     exposes MCP-HTTP at :8090        │
                │     dashboard at :8092 for setup     │
                └──────────────────────────────────────┘
                          ▲   ▲   ▲   ▲
                          │   │   │   │  MCP-HTTP
                          │   │   │   │  (one stable wire format)
            ┌─────────────┴───┴───┴───┴───────────┐
            │      agents — pure MCP clients      │
            │      no Python, no plugin shims     │
            │      no per-runtime install code    │
            │                                     │
            │      Each agent has ONE thing:      │
            │      a single MD file that tells    │
            │      the LLM what tools exist and   │
            │      how to call them.              │
            │                                     │
            │  zeroclaw  openclaw  hermes  claude │
            └─────────────────────────────────────┘

One install (the container). One stable interface (MCP-HTTP).
Skill author is upstream of agents instead of downstream.
Agent runtimes evolve freely — as long as they keep speaking MCP,
the service stays compatible. No per-runtime maintenance tax.
```

---

## What changes for the skill author

**Before, my repo had:**

- `installers/zeroclaw/install.sh` (~250 lines, patches autonomy gates, runs uv sync, symlinks binary)
- `installers/openclaw/install.sh` (~310 lines, drives `openclaw config patch`, writes plugin manifest, seeds bootstrap workspace, runs npm install for the TS plugin)
- `installers/hermes/install.sh` (~100 lines, extracts to `~/.hermes/skills/`, sets up venv, manages PATH)
- `dist/index.js` — compiled openclaw TS plugin shim (22 KB, regenerated on every change)
- `openclaw.plugin.json` — manifest in the openclaw 4.29-beta.4 schema (with the new JSON-Schema `configSchema` and `activation` block we discovered the hard way)
- `package.json` + `package-lock.json` — npm metadata that exists *only* because the openclaw plugin loader needs `node_modules/`
- `.skillignore` — zeroclaw skill audit ignores
- `SKILL.toml` — zeroclaw skill manifest
- `KNOWN_ISSUES.md` — workarounds for openclaw 4.27 auth regression, zeroclaw 0.7.3 autonomy gates, hermes meta-tool indirection
- A make target (`make skill-bundle`) that whitelists which files actually go into the audit-compliant tarball
- A `setup.sh` that detected which runtime was present and dispatched

That's about **2,090 lines of install plumbing**. None of it computes Sharpe ratios. None of it talks to FRED. None of it parses an Excel statement. All of it exists because the skill has to land in four different runtimes that each understand "skill" differently.

**After, my repo has:**

- `compose.yml` (~100 lines, MIT-licensed, pulled from a stable URL by the user)
- `SKILL.md` (~200 lines, MIT-licensed, describes the MCP tool surface in prose, drops into `~/.<agent>/skills/` for runtimes that consume markdown skill docs, or just lives at the URL for runtimes that don't)
- `Dockerfile` (~60 lines, builds the service)
- The bridge code (~800 lines of Python that wraps existing CLI verbs as MCP tools)

That's it. One service. One distribution edge. The whole "make this work on zeroclaw vs openclaw vs hermes vs claude code" branch of the codebase doesn't exist anymore.

The user-side install collapses to:

```bash
docker compose -f https://get.investorclaw.app/v4.0/compose.yml up -d
```

Or, if zeroclaw lands the upstream PR I'm proposing:

```bash
zeroclaw services install https://get.investorclaw.app/v4.0/compose.yml
```

That's the entire install. No skill bundle, no plugin manifest, no pyproject.toml, no uv.lock to keep current, no bootstrap workspace seeding, no per-OS PATH symlinks, no audit-rule chasing. The agent's local config gets one entry — a URL — and the rest is HTTP.

---

## Why this isn't a new spec

I'm not proposing a new protocol, a new manifest format, or a new standards body. The components already exist:

- **MCP** (Model Context Protocol — Anthropic-stewarded, broadly adopted across agent runtimes) handles the wire-level "agent talks to a tool server" problem. We use it as-is, unmodified.
- **Docker Compose** handles the deployment shape. We use it as-is, including its existing `x-*` extension key mechanism (which Compose ignores by design but tools can read).

What's *new* is just a documented *convention* for putting the MCP server manifest into the compose file's `x-*` keys, so a tool reading the compose can know which MCP servers to register without out-of-band knowledge:

```yaml
x-mcp-services:
  investorclaw:
    transport: http
    url: http://127.0.0.1:8090/mcp
    description: "Portfolio analysis (deterministic, FINOS CDM 5.x)"
    health: http://127.0.0.1:8090/healthz

x-mcp-service-meta:
  spec: "compose-x-mcp-services/v1"
  version: "4.0"
  dashboard_url: http://127.0.0.1:8092/
  optional_keys:
    - { name: TOGETHER_API_KEY, purpose: "narrative LLM" }
    - { name: FINNHUB_KEY,      purpose: "real-time quotes" }

services:
  ic-engine:
    image: mnemos-os/ic-engine:4.0
    ports: ["8090:8090", "8092:8092"]
    volumes: [data:/data]
```

Compose ignores `x-mcp-services` and `x-mcp-service-meta` and starts the `services` block. Tools that implement the convention read the `x-*` blocks and wire up the agent's MCP config. **Adoption is a README, not a working group.**

This is the Helm-for-MCP shape. Helm became the de facto Kubernetes package manager not by inventing a new container format but by writing a thin, useful convention on top of existing pieces. We can do the same for MCP services.

---

## Why zeroclaw is the right reference implementation

Two reasons. First, **zeroclaw already has the primitives**:

- `[runtime.docker]` config block + `DockerSandbox` Rust class (PR #5905 in flight on master) — the container runtime is already there
- `[mcp]` config schema with `[mcp.servers.<name>]` blocks on master — MCP-server registration is already there
- Single Rust binary, lean footprint, low-overhead — the right execution model for "package manager"

Adding `zeroclaw services install <compose-url>` is glue code that builds on existing components. I estimate ~300-500 LOC of Rust on top of `DockerSandbox`. It's not a new subsystem; it's a thin orchestration layer.

Second, **it's the right strategic positioning for zeroclaw**:

> *"openclaw is the polished gateway. Hermes is the multimodal research agent. Claude Code is Anthropic's IDE-grade tool. **zeroclaw is the one that runs your MCP services.**"*

Differentiation. Distinct value. And honestly — given that you (the zeroclaw team) maintain a Rust-only codebase explicitly *because* you don't want to absorb the operational complexity of Python ecosystems, this is a perfect fit. You don't have to integrate Python; the Python lives in *its own container*. Your Rust code orchestrates installation. Skill authors keep their messy native-extension dependency trees in their own user-space.

---

## What this looks like for non-trivial skills

The dockerized-skill convention is most useful for skills that are **non-trivial code bundles**. If your skill is "have the LLM write a 5-line Python script to compute X" — by all means, just have the LLM write the script. That works.

But the moment your skill has:

- **A serious dependency tree** (numpy / pandas / scipy / native libraries / etc.)
- **Persistent state** (sqlite cache, uploaded files, computed reports)
- **A configuration surface** (provider API keys, account hierarchies, narrative tier preferences)
- **A reasonable expectation of behaving the same in 6 months as it does today**

…then making it survive agent runtime upgrades by giving it its own user-space is the right move. Ship a container. Ship an MCP server. Ship a markdown file. Be done.

I'd argue this applies broadly:

- **Risk analysis tools** that need pandas / scipy
- **Research pipelines** with web-scraping deps
- **Code-execution sandboxes** with their own runtimes
- **Domain-specific compute services** (legal-doc parsing, scientific simulation, geospatial analysis)
- **Anything that wraps an existing Python/JS/native library and exposes its surface to agents**

The pattern generalizes. Each skill becomes a standalone service, MCP being the universal join.

---

# RFC: `compose-x-mcp-services` convention

**Status:** Draft v0.1
**Author:** Jason Perlow
**Date:** 2026-05-01
**License:** This RFC is CC-BY-4.0; the reference implementation is Apache 2.0; distribution-edge artifacts (compose.yml, install.yaml, SKILL.md) are MIT.

## 1. Abstract

`compose-x-mcp-services` is a **documented convention** for distributing
MCP services as Docker Compose stacks. It uses Docker Compose's existing
`x-*` extension-key mechanism (which Compose ignores by design but tools
can read) to carry an MCP-server manifest alongside the service
definitions in a single `compose.yml`. Tools implementing the convention
can install, start, stop, upgrade, and uninstall MCP services from a
single compose URL. The convention adds **no new protocol** to MCP and
**no new format** to Docker Compose — it's purely a layered standard
on top of two existing standards.

## 2. Motivation

Skill authors building non-trivial agentic code bundles (significant
dependency trees, persistent state, configuration surfaces) currently
have to ship per-agent-runtime install paths. Each agent runtime's
install conventions evolve independently and break frequently.
Empirical evidence from a fleet barrage on 2026-04-30 (TYPHON
Windows-WSL Docker, InvestorClaw v2.6.3): openclaw 4.29-beta.4 21/30,
zeroclaw 0.7.x 6/30, hermes 0.12 6/30 — every regression was install
friction, not analytical bugs.

The convention inverts the dependency: skills run in their own
containers, expose their surface via MCP, and become invariant to
agent runtime changes as long as the runtime continues to speak MCP.

## 3. Definitions

- **MCP service**: a containerized program that exposes one or more
  MCP servers (over HTTP, stdio, or SSE transports).
- **Service author**: the maintainer of an MCP service (e.g., the
  InvestorClaw maintainer).
- **Install tool**: an agent runtime or CLI that consumes a compose
  URL, brings up the containers, and registers the MCP servers in
  the agent's configuration. Reference implementation: `zeroclaw
  services install`.
- **Compose URL**: a stable HTTPS URL serving a `compose.yml` file
  authored according to this convention.

## 4. Goals

- Skill authors publish ONE compose URL; install tools handle the rest
- Agent runtimes can adopt the convention with ~hundreds of LOC of
  glue, building on existing Docker + MCP primitives
- Service authors retain freedom to use any language / dependency
  tree inside their container
- Convention layers on top of MCP (transport, tool catalog) and
  Docker Compose (deployment) without modifying either
- Adoption is voluntary and incremental; consuming tools that don't
  implement the convention can still run the compose with stock
  `docker compose up` (the `x-*` keys are ignored)

## 5. Non-Goals

- Not a replacement for MCP itself
- Not a new container runtime or orchestration layer
- Not a centralized registry, marketplace, or trust system (those
  can layer on top later if useful)
- Not a packaging format for MCP services that don't run in
  containers (services packaged as npm modules or single binaries
  remain valid; this convention is specifically for compose-shipped
  services)

## 6. Convention specification (v1)

### 6.1 The compose file

A compose file conforming to this convention MUST include a top-level
`x-mcp-services` extension key. It SHOULD include a top-level
`x-mcp-service-meta` extension key.

### 6.2 `x-mcp-services`

A YAML object mapping MCP server names to their configuration:

```yaml
x-mcp-services:
  <server-name>:
    transport: http | stdio | sse        # required, one of
    url: http://127.0.0.1:<port>/mcp     # required if transport=http or sse
    command: <executable>                # required if transport=stdio
    args: [<arg1>, <arg2>, ...]          # optional, stdio only
    description: <human-readable string> # optional
    health: http://127.0.0.1:<port>/healthz  # optional, HTTP probe URL
```

The `<server-name>` becomes the namespace under which the agent
registers the MCP server. Names MUST match `^[a-z][a-z0-9_-]*$` to
satisfy MCP / OpenAI tool-name validation across runtimes.

### 6.3 `x-mcp-service-meta`

A YAML object describing the service as a whole:

```yaml
x-mcp-service-meta:
  spec: "compose-x-mcp-services/v1"   # required, identifies convention version
  version: <service-version>           # required, semver of the service
  dashboard_url: <http URL>            # optional, user-facing config UI
  bundle_url: <http URL>               # optional, install spec for non-Docker-native installers
  skill_url: <http URL>                # optional, agent-readable instructions
  required_keys: [...]                 # optional, list of required env-var names
  optional_keys:                       # optional, list of optional env-var names with descriptions
    - { name: <KEY_NAME>, purpose: <description> }
  preferred_agents: [...]              # optional, advisory list of preferred agent runtimes
  supported_agents: [...]              # optional, advisory list of supported agent runtimes
```

### 6.4 Agent-side artifact

A service following this convention MAY publish a single MIT-licensed
`SKILL.md` document (referenced via `x-mcp-service-meta.skill_url`)
that the install tool MAY drop into the agent's skill directory, if
the agent runtime has one. The SKILL.md describes the service's MCP
tool surface in prose for the LLM to reference. It MUST NOT contain
executable code, scripts, or symlinks. It MUST be MIT-licensed (or a
similarly permissive license) to enable frictionless redistribution
across agent skill marketplaces.

The Apache 2.0 / MIT split exists because the substantive code (the
service implementation) and the distribution-edge artifacts (compose,
SKILL.md) serve different audiences. Substantive code typically
benefits from Apache's patent grant. Distribution-edge files benefit
from MIT's permissiveness when redistributed across agent marketplaces.

## 7. Install tool obligations

A tool implementing the install side of this convention SHOULD support
these operations:

- **`install <compose-url>`**: fetch the compose, parse `x-mcp-services`,
  bring up the services (`docker compose up -d` or equivalent), wait
  on health probes, write the agent's MCP server config block.
- **`list`**: enumerate installed services with status.
- **`uninstall <name>`**: stop the services, remove the MCP server
  config block, optionally remove the volume.
- **`upgrade <name>`**: re-fetch the compose URL (or a specified
  newer URL), pull updated images, restart, preserve the volume.

Install tools MAY support additional operations (e.g., `start`,
`stop`, `logs`, `inspect`).

## 8. Security considerations

- **API keys are not part of bundle data flowing through this
  convention.** Service configuration (provider API keys, etc.)
  lives in the service's own data volume, not in the compose file
  or in the agent's MCP config. Bundle files referenced via
  `bundle_url` MUST hold only env-var references (e.g.,
  `"$TOGETHER_API_KEY"`), never raw values.
- **Default port binding SHOULD be localhost-only.** Service authors
  who publish compose files for the public SHOULD bind to
  `127.0.0.1:<port>` by default, with documented overrides for
  remote-access scenarios (Tailscale, behind nginx, etc.).
- **Container-to-container networking SHOULD use compose's bridge
  network.** Services that interact (e.g., a memory service +
  analytical service) communicate over the compose-internal network,
  not via host networking.
- **Auth tokens for remote-access deployments SHOULD be opt-in.**
  Localhost-only deployments need no auth; remote deployments SHOULD
  require a bearer token, and the install tool SHOULD generate one
  on first install.

## 9. Versioning

The convention is versioned via `x-mcp-service-meta.spec`. v1 is
defined by this RFC. v2+ MAY add optional fields; install tools
SHOULD treat unknown fields as informational and continue.
Breaking changes to existing field semantics REQUIRE a new major
version (`compose-x-mcp-services/v2`).

## 10. Prior art

- **Helm charts** (Apache 2.0) for Kubernetes (Apache 2.0): same
  shape — a thin convention layered over an existing container
  orchestration layer, with an extension-key manifest carrying the
  package's metadata.
- **MCP server registries** (Smithery, mcp-installer, others):
  these solve the discovery + install problem via npm-based
  package distribution. The compose convention solves it via
  container distribution. They're complementary; an MCP service
  could ship via both channels.
- **Docker Compose's `x-*` extension keys**: the existing
  Compose mechanism we're using. Already widely understood.

## 11. Reference implementation

- **InvestorClaw v4.0** (`mnemos-os/mnemos-ic-runtime`): the first
  reference service implementing the convention. Apache 2.0 service
  code; MIT distribution-edge artifacts. ~2,400 LOC, 44 passing
  tests, scaffolded as of 2026-05-01. Beta pilot ships within 24
  hours of this RFC's publication.
- **`zeroclaw services install`** (proposed PR against
  `zeroclaw-labs/zeroclaw`): the first reference install tool.
  ~300-500 LOC of Rust on top of existing `DockerSandbox` and
  `[mcp]` config schema. PR target after 2026-05-01.

## 12. Open questions

- **How does an install tool authenticate against private compose
  URLs?** Initial answer: out of scope; use bearer-token-protected
  HTTPS endpoints, install tool consumes via `Authorization`
  header. Future RFCs may formalize.
- **How does the convention handle services that need multiple MCP
  servers?** Already handled: `x-mcp-services` is a map; multiple
  entries are valid.
- **How does the convention handle services that consume *other*
  MCP services (composition / chaining)?** Out of scope for v1.
  Inter-service dependencies are managed via compose's `depends_on`
  and shared environment variables.
- **What about non-Docker container runtimes (Podman, containerd,
  systemd-nspawn)?** All of those run docker-compose-format files.
  No changes needed.

## 13. Adoption path

1. **Service authors**: publish your `compose.yml` with the `x-*`
   keys at a stable URL. Optionally publish a SKILL.md alongside.
   Even without any tooling support, your users can `docker compose
   up -d` against your URL today.
2. **Agent-runtime maintainers**: implement an install tool that
   reads the convention. ~hundreds of LOC; reuses your existing
   container + MCP primitives.
3. **Service authors and runtime maintainers, together**:
   coordinate on shared registry / discovery mechanisms in future
   RFC versions if there's appetite. v1 deliberately avoids this
   to minimize adoption friction.

---

## Closing — what I'm shipping

I'm shipping InvestorClaw v4.0 against this convention within 24
hours of this post. The repository is at
`https://github.com/mnemos-os/mnemos-ic-runtime` (creating it now).
The v4.0 RFC document, full bridge code, Pydantic bundle schema,
HTML setup form, and Dockerfile are already drafted and committed
locally. 44/44 tests passing.

If you maintain an agent runtime, a code-bundle skill, or a
research pipeline that's been fighting agent install conventions:
**this might fit your problem too**. I'd love feedback on the RFC
above, especially on the security considerations and the
versioning scheme.

If you maintain zeroclaw (`@nclawzero` team), I'd like to draft
the `services install` PR against your master. Let me know if the
proposal lands cleanly or if there are adjustments you'd want
before I write Rust against it.

If you're a developer at any of the other agent runtimes, the
convention is open. The reference impl is in zeroclaw, but
nothing about the convention is zeroclaw-specific.

The pattern is the answer to a real pain. The faster the
agentic-AI ecosystem converges on stable boundaries between
"agent runtime evolves fast" and "skill code stays stable," the
faster everyone ships work that survives.

Comments, objections, refinements: I'm listening.

— *Jason*

---

*InvestorClaw is a portfolio analysis service. Educational use only —
not investment advice. Code under Apache 2.0; distribution-edge
artifacts under MIT.*
