# Security TEE Hub

A Cursor workspace that connects to JIRA, Confluence, and GitHub via MCP -- so you can investigate security escalations without switching between browser tabs.

---

## Setup (5 minutes)

### 1. Clone and open in Cursor

```
git clone git@github.com:DataDog/security-tee-hub.git
```

Open the folder in [Cursor](https://cursor.com).

### 2. Configure credentials

```bash
cp .env.example .env
cp .cursor/mcp.json.example .cursor/mcp.json
```

Edit both files with your details:

- **Atlassian token** -- create one at [id.atlassian.com/manage-profile/security/api-tokens](https://id.atlassian.com/manage-profile/security/api-tokens)
- **GitHub token** (optional) -- create a [fine-grained PAT](https://github.com/settings/tokens?type=beta) with Contents + Metadata read; authorize SSO for DataDog org

### 3. Install uv (MCP server runner)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 4. Restart Cursor

Quit completely (Cmd+Q), reopen. MCP only loads on startup.

Test it: *"Use MCP to fetch JIRA ticket SCRS-1885"*

---

## What you can do

| Goal | What to say |
|------|-------------|
| Investigate an escalation | "Investigate SCRS-1949" |
| Search past escalations | "Search JIRA for CSPM false positive issues" |
| Find internal docs | "Search Confluence for agent flare troubleshooting" |
| Search code | "Search GitHub for this error in DataDog/datadog-agent" |
| Draft a TEE response | "Draft a response for this investigation" |
| Check similar cases | "Search the archive for similar issues" |
| Archive done tickets | "Archive this investigation" |

---

## Local Web UI

Run `./app/run.sh` to launch a browser-based dashboard for browsing investigations, archive, and docs. Entirely optional -- the workspace works fully through Cursor alone.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "I don't have access to JIRA" | Check your Atlassian token in `.cursor/mcp.json`, restart Cursor |
| "uvx not found" | Run the install command above, then `source ~/.zshrc` |
| GitHub not working | Token expired -- regenerate and update `.cursor/mcp.json` |
| Cursor slow on first open | Wait for indexing to finish |

For anything else: tell Cursor *"Help me troubleshoot my MCP setup"*

---

## Need help?

- Ask Cursor -- it knows how the workspace works
- Slack: #tee-security
- Repo: [github.com/DataDog/security-tee-hub](https://github.com/DataDog/security-tee-hub)
