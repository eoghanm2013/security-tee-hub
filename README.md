# Security TEE Hub

Centralized workspace for Technical Escalation Engineering on Datadog Security Products.

> **New here?** Follow the **[Setup Guide](SETUP.md)** for step-by-step instructions.

---

## Quick Start

### 1. Clone the repo
```bash
git clone git@github.com:YOUR_ORG/security-tee-hub.git
cd security-tee-hub
```

### 2. Set up credentials

**Environment variables:**
```bash
cp .env.example .env
# Edit .env with your Atlassian token and email
```

**MCP config (for Cursor AI integration):**
```bash
cp .cursor/mcp.json.example .cursor/mcp.json
# Edit .cursor/mcp.json with your tokens
```

### 3. Install dependencies
```bash
# Install uv (for MCP servers)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Verify installation
~/.local/bin/uvx --version
```

### 4. Restart Cursor
After setting up MCP config, restart Cursor completely (Cmd+Q, reopen).

### 5. Test it works
Ask Cursor:
> "Use MCP to fetch JIRA ticket SCRS-1234"

---

## Structure

```
security-tee-hub/
├── .cursor/
│   ├── mcp.json              # YOUR config (gitignored)
│   └── mcp.json.example      # Template for setup
├── .cursorrules              # AI behavior rules
├── investigations/           # Active escalations
│   ├── .template/            # Copy for new investigations
│   └── SCRS-XXXX/            # One folder per case (gitignored)
├── archive/                  # Archived tickets (gitignored)
├── docs/                     # Internal documentation
├── ideas/                    # Future project ideas
├── scripts/                  # Utility scripts
└── reference/                # Reference materials
```

---

## Getting API Tokens

### Atlassian (JIRA & Confluence)
1. Go to: https://id.atlassian.com/manage-profile/security/api-tokens
2. Create new token
3. Add to `.env` and `.cursor/mcp.json`

### GitHub
1. Go to: https://github.com/settings/tokens?type=beta
2. Create fine-grained token with scopes:
   - `Contents` (read)
   - `Metadata` (read)
3. For Datadog org repos, authorize SSO
4. Add to `.cursor/mcp.json`

---

## MCP Integration

This workspace uses Model Context Protocol (MCP) to give Cursor direct access to:
- **JIRA** — Fetch tickets, search history
- **Confluence** — Read internal documentation
- **GitHub** — Search Datadog codebases

### MCP Config Format
See `.cursor/mcp.json.example` for the template. Key settings:
- `--read-only` flag enabled by default (safe)
- Credentials passed as CLI arguments

### If MCP doesn't work
Fall back to the Python scripts:
```bash
python scripts/jira_client.py get SCRS-1234
python scripts/jira_client.py search "project = SCRS AND status = Open"
```

---

## Workflow

### Starting an Investigation

**Option 1: Ask Cursor**
> "Investigate SCRS-1234"

Cursor will:
1. Fetch the ticket
2. Assess escalation quality
3. Search for similar cases
4. Create investigation notes

**Option 2: Manual**
```bash
cp -r investigations/.template investigations/SCRS-1234
```

### During Investigation
- Cursor pulls live JIRA data via MCP
- Drop logs, flares, screenshots into `assets/`
- Document findings in `notes.md`
- Cursor searches archive for similar past issues

### Archiving
```bash
python scripts/jira_client.py archive SCRS-1234
# OR bulk archive:
python scripts/bulk_archive.py --days 90
```

---

## Scripts

### jira_client.py
```bash
# Get a single issue
python scripts/jira_client.py get SCRS-1234

# List open issues
python scripts/jira_client.py list-open

# Search with JQL
python scripts/jira_client.py search "status = 'Waiting for TSE'"

# Archive an issue
python scripts/jira_client.py archive SCRS-1234
```

### bulk_archive.py
```bash
# Archive last 90 days (with safety check)
python scripts/bulk_archive.py --days 90

# Skip confirmation
python scripts/bulk_archive.py --days 30 --yes
```

---

## Safety

⚠️ **READ-ONLY by default**

- MCP configs use `--read-only` flag
- Cursor will NOT write to Atlassian/GitHub unless you explicitly ask
- All credentials stay local (gitignored)

---

## Product Areas

| Area | Description |
|------|-------------|
| **AppSec** | Application Security, ASM, WAF, API Security |
| **SIEM** | Cloud SIEM, detection rules, signals |
| **CWS** | Cloud Workload Security, runtime security |
| **CSPM** | Cloud Security Posture Management |
| **VM** | Vulnerability Management |
| **SCA** | Software Composition Analysis |
| **IAST** | Interactive Application Security Testing |
| **SAST** | Static Application Security Testing |

---

## Troubleshooting

### MCP not loading
1. Verify config exists: `cat .cursor/mcp.json`
2. Check uvx installed: `~/.local/bin/uvx --version`
3. Restart Cursor completely (Cmd+Q)
4. Check Cursor's MCP panel for errors

### API errors
| Code | Issue | Fix |
|------|-------|-----|
| 401 | Bad token | Regenerate API token |
| 403 | No permissions | Check token scopes |
| 410 | API deprecated | Update scripts |

### JIRA search returns wrong results
The SCRS project's "Issue Type" field is unreliable. Search by content, labels, or status instead.

---

## Contributing

1. Keep sensitive data out of commits (`.gitignore` handles this)
2. Document new scripts/features
3. Share investigation learnings via `docs/`
