# Métis Multi-Client MCP Integration
## Claude First, Copilot in Parallel — Concrete Configuration, Not Just Positioning

---

## 0. Why this works for both without server-side branching

Métis's `mcp-server` component (the Helm chart's `mcp-server` deployment) speaks standard **MCP over Streamable HTTP** with OAuth2 authorization. This is the whole point of MCP as a protocol — the server doesn't know or care whether the caller is Claude Code, Claude Desktop, or GitHub Copilot's Agent mode. What differs between clients is entirely **client-side configuration**: how each one is told the server exists and how each one obtains a token. Everything after that — the current tool set, the RBAC scoping, the token lifecycle (`CONST-064`) — is identical.

---

## 1. Claude — connect this first

### Claude Code (project-scoped `.mcp.json`)

Add to the project's `.mcp.json` (or run `claude mcp add` interactively):

```json
{
  "mcpServers": {
    "metis": {
      "url": "https://REPLACE-metis-host.example.com/mcp",
      "transport": "http",
      "auth": {
        "type": "oauth2",
        "authorizationUrl": "https://REPLACE-metis-host.example.com/oauth/authorize",
        "tokenUrl": "https://REPLACE-metis-host.example.com/oauth/token",
        "scopes": ["metis:read"]
      }
    }
  }
}
```

`metis:read` scopes to the read-only tool set (`metis_get_context`, `metis_get_traceability`, `metis_check_coverage`, `metis_impact_analysis`, `metis_explain_decision`, `metis_explain_answer`) — matching §11.1's default-enabled set. Don't request a write scope (`metis:write`, gating `metis_submit_episode`) until the org has actually opted into the write path per `REQ-METIS-CPT-01`.

On first use, Claude Code will prompt an interactive OAuth2 authorization — approve it once per user, the resulting token is cached client-side and refreshed automatically per `CONST-064`'s 30-day refresh window.

### Claude Desktop (custom connector)

Settings → Connectors → Add custom connector → same URL and OAuth2 details as above. Functionally identical to the Claude Code path; the difference is purely which Claude surface you're working from.

### Headless / CI usage (Claude Code non-interactively)

For CI contexts where an interactive OAuth2 approval isn't possible, use the PAT/Bearer path instead (§11.5 of the master spec):

```json
{
  "mcpServers": {
    "metis": {
      "url": "https://REPLACE-metis-host.example.com/mcp",
      "transport": "http",
      "auth": {
        "type": "bearer",
        "token": "${METIS_CI_TOKEN}"
      }
    }
  }
}
```

`METIS_CI_TOKEN` should be a service-account token scoped read-only, issued and rotated the same way any other CI credential is — not a personal user token checked into pipeline config.

---

## 2. Copilot — same server, added in parallel

Copilot's discovery convention is a prebuilt agent file rather than a raw `.mcp.json` entry — this is Copilot's own convenience layer, not a different server or permission model:

```markdown
---
name: spec-aware
tools: ["metis_get_context", "metis_get_traceability", "metis_check_coverage",
        "metis_impact_analysis", "metis_explain_decision", "metis_explain_answer"]
mcp_server: "https://REPLACE-metis-host.example.com/mcp"
auth: oauth2
---
```

Reachable only in Copilot **Agent mode** (a real Copilot-side constraint, not a Métis one) — matching `REQ-METIS-CPT-04`.

---

## 3. What actually differs between the two clients (so you know what to expect when you compare results)

| | Claude | Copilot |
|---|---|---|
| Default traversal depth | 3 hops | 2 hops |
| Context budget | 1M-token-class (Claude Code/Sonnet-5+) | Smaller — retrieval sized down, not truncated late |
| Discovery convention | `.mcp.json` / custom connector | `spec-aware.agent.md` |
| Non-interactive auth | PAT/Bearer available | OAuth2 only (no documented headless path yet) |
| Everything else (tools, RBAC, guardrails, write-gate) | Identical | Identical |

If Claude testing surfaces a tool behaving differently than expected, the traversal-depth and context-budget differences above are the first thing to check before assuming a server-side bug — a 3-hop vs. 2-hop default genuinely changes what `metis_impact_analysis` returns for the same query.

---

## 4. What's genuinely still open

| Item | Status |
|---|---|
| Actual OAuth2 provider (self-hosted, or an existing org IdP) | Not chosen here — `REPLACE`d throughout; both client configs work identically regardless of which provider issues the tokens |
| Whether Copilot gets a headless/CI path of its own eventually | Not designed here — flagged as an asymmetry worth revisiting once Claude's CI usage proves the pattern out |
| Real hostname/TLS setup | Matches the Helm chart's `ingress.host`/`ingress.tls` values — fill in together, not independently |
