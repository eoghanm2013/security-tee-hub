# 🚀 Security TEE Hub - Setup Guide

This guide will get you up and running in ~10 minutes.

---

## Prerequisites

Before starting, make sure you have:

- [ ] **Cursor IDE** installed ([cursor.com](https://cursor.com))
- [ ] **Git** installed
- [ ] **Python 3.8+** installed
- [ ] Access to **Datadog's Atlassian** (JIRA/Confluence)
- [ ] Access to **Datadog's GitHub org**

---

## Step 1: Clone the Repository

```bash
git clone git@github.com:DataDog/security-tee-hub.git
cd security-tee-hub
```

---

## Step 2: Install `uv` (MCP Server Runner)

The MCP servers run via `uvx`. Install it:

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Verify installation
~/.local/bin/uvx --version
```

If the command isn't found, add to your shell profile:
```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

---

## Step 3: Get Your API Tokens

### Atlassian Token (JIRA & Confluence)

1. Go to: https://id.atlassian.com/manage-profile/security/api-tokens
2. Click **"Create API token"**
3. Name it: `TEE Hub`
4. Copy the token (you won't see it again!)

### GitHub Token

1. Go to: https://github.com/settings/tokens?type=beta
2. Click **"Generate new token"**
3. Name it: `TEE Hub`
4. Set expiration (90 days recommended)
5. Under **"Repository access"**, select: `All repositories` (or specific Datadog repos)
6. Under **"Permissions"**, enable:
   - `Contents` → Read-only
   - `Metadata` → Read-only
7. Click **"Generate token"**
8. **Important:** If accessing Datadog private repos, click **"Configure SSO"** and authorize for DataDog org

---

## Step 4: Configure Environment Variables

```bash
# Copy the template
cp .env.example .env

# Edit with your values
nano .env  # or use your preferred editor
```

Fill in your details:
```bash
ATLASSIAN_EMAIL=your.name@datadoghq.com
ATLASSIAN_DOMAIN=datadoghq.atlassian.net
ATLASSIAN_API_TOKEN=paste_your_atlassian_token_here

JIRA_PROJECT_KEY=SCRS

GITHUB_TOKEN=paste_your_github_token_here
```

Save and close.

---

## Step 5: Configure MCP (Cursor AI Integration)

This is the magic that lets Cursor talk directly to JIRA, Confluence, and GitHub.

```bash
# Copy the template
cp .cursor/mcp.json.example .cursor/mcp.json

# Edit with your values
nano .cursor/mcp.json
```

Replace the placeholders:

```json
{
  "mcpServers": {
    "atlassian": {
      "command": "uvx",
      "args": [
        "mcp-atlassian",
        "--jira-url", "https://datadoghq.atlassian.net",
        "--jira-username", "YOUR_EMAIL@datadoghq.com",      ← Replace
        "--jira-token", "YOUR_ATLASSIAN_TOKEN",             ← Replace
        "--confluence-url", "https://datadoghq.atlassian.net/wiki",
        "--confluence-username", "YOUR_EMAIL@datadoghq.com", ← Replace
        "--confluence-token", "YOUR_ATLASSIAN_TOKEN",        ← Replace
        "--read-only"
      ]
    },
    "github": {
      "command": "uvx",
      "args": ["mcp-github"],
      "env": {
        "GITHUB_TOKEN": "YOUR_GITHUB_TOKEN"                  ← Replace
      }
    }
  }
}
```

Save and close.

---

## Step 6: Restart Cursor

**Important:** MCP only loads when Cursor starts.

1. Quit Cursor completely: **Cmd+Q** (not just close window)
2. Reopen Cursor
3. Open this project folder

---

## Step 7: Verify Everything Works

Open Cursor and test each integration:

### Test JIRA
Ask Cursor:
> "Use MCP to fetch JIRA ticket SCRS-1885"

**Expected:** Cursor shows ticket details (summary, status, description)

### Test Confluence
Ask Cursor:
> "Search Confluence for security troubleshooting"

**Expected:** Cursor returns matching pages

### Test GitHub
Ask Cursor:
> "Search GitHub for 'broken pipe' in DataDog/libdatadog"

**Expected:** Cursor returns code results

### Test Python Scripts (Fallback)
```bash
# Make sure you're in the project directory
cd security-tee-hub

# Test JIRA script
python scripts/jira_client.py list-open
```

**Expected:** List of open SCRS tickets

---

## 🎉 You're Ready!

Try your first investigation:
> "Investigate SCRS-1885"

Cursor will:
1. Fetch the ticket from JIRA
2. Assess the escalation quality
3. Search for similar historical cases
4. Generate investigation notes

---

## Troubleshooting

### MCP not loading

**Symptom:** Cursor doesn't recognize JIRA/GitHub commands

**Fix:**
1. Check config exists: `cat .cursor/mcp.json`
2. Verify JSON is valid (no trailing commas, quotes correct)
3. Check uvx works: `~/.local/bin/uvx --version`
4. Fully restart Cursor (Cmd+Q, not just close)

### "uvx not found"

**Fix:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.zshrc  # or restart terminal
```

### JIRA 401 Unauthorized

**Symptom:** `HTTP Error 401`

**Fix:**
1. Regenerate your Atlassian API token
2. Update `.cursor/mcp.json` with new token
3. Restart Cursor

### GitHub 401 or 403

**Symptom:** GitHub searches fail

**Fix:**
1. Check token hasn't expired
2. For Datadog repos: Authorize SSO at https://github.com/settings/tokens
3. Update `.cursor/mcp.json` with new token
4. Restart Cursor

### Python scripts fail

**Symptom:** `ModuleNotFoundError` or API errors

**Fix:**
```bash
# Check Python version
python --version  # Should be 3.8+

# Scripts use standard library only, no pip install needed
# Check .env is correct
cat .env
```

---

## File Structure After Setup

```
security-tee-hub/
├── .cursor/
│   ├── mcp.json              ← Your config (gitignored)
│   └── mcp.json.example      ← Template
├── .env                      ← Your tokens (gitignored)
├── .env.example              ← Template
├── .cursorrules              ← AI behavior rules
├── investigations/
│   └── .template/            ← Copy for new cases
├── archive/                  ← Will fill with archived tickets
├── docs/                     ← Troubleshooting docs
├── ideas/                    ← Future projects
├── scripts/                  ← Python utilities
└── README.md
```

---

## Getting Help

- **Slack:** #tee-security (or your team channel)
- **Issues:** Open a GitHub issue on this repo
- **Cursor:** Just ask! The AI knows how this hub works

---

## Optional: Bulk Archive Historical Tickets

To seed your local archive with historical data:

```bash
# Archive last 30 days (safe, with confirmation)
python scripts/bulk_archive.py --days 30

# Archive last 90 days (will prompt if > 500 tickets)
python scripts/bulk_archive.py --days 90
```

This gives Cursor historical context to find similar past cases.

---

Happy investigating! 🔍

