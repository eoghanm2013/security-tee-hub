# Security TEE Hub

A Cursor workspace that connects to JIRA, Confluence, GitHub, and Glean via MCP -- so you can investigate security escalations without switching between browser tabs.

---

## Setup (2 minutes)

### 1. Clone and open in Cursor

```
git clone git@github.com:DataDog/security-tee-hub.git
```

Open the folder in [Cursor](https://cursor.com).

### 2. Tell Cursor: "Set me up"

That's it. The setup script configures everything:

- **Atlassian** (JIRA + Confluence) -- uses SSO, no token needed
- **Glean** (Slack, internal docs) -- uses SSO, no token needed
- **GitHub** (optional) -- needs a [PAT](https://github.com/settings/tokens?type=beta) with Contents + Metadata read; authorize SSO for DataDog org

### 3. Restart Cursor

Quit completely (Cmd+Q), reopen. Atlassian and Glean will prompt a one-time SSO login on first use.

Test it: *"Use MCP to fetch JIRA ticket SCRS-1885"*

---

## What you can do

| Goal | What to say |
|------|-------------|
| Investigate an escalation | "Investigate SCRS-1949" |
| Search past escalations | "Search JIRA for CSPM false positive issues" |
| Find internal docs | "Search Confluence for agent flare troubleshooting" |
| Search code | "Search GitHub for this error in DataDog/datadog-agent" |
| Search everything | "Search Glean for recent security product updates" |
| Draft a TEE response | "Draft a response for this investigation" |
| Check similar cases | "Search the archive for similar issues" |
| Archive done tickets | "Archive this investigation" |

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "I don't have access to JIRA" | Restart Cursor (Cmd+Q), SSO will re-prompt |
| GitHub not working | Token expired -- tell Cursor "reconfigure my workspace" |
| Cursor slow on first open | Wait for indexing to finish |

For anything else: tell Cursor *"Help me troubleshoot my MCP setup"*

---

## Need help?

- Ask Cursor -- it knows how the workspace works
- Slack: #tee-security
- Repo: [github.com/DataDog/security-tee-hub](https://github.com/DataDog/security-tee-hub)
