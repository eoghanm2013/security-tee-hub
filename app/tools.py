"""
Chat tools for TEE Hub AI assistant.

Provides functions the LLM can call mid-conversation to fetch data
from JIRA, search local investigation files, etc.

Each function returns a plain string (the LLM reads the result and
incorporates it into its answer).
"""

import os
import re
import json
import base64
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
INVESTIGATIONS_DIR = ROOT / "investigations"
ARCHIVE_DIR = ROOT / "archive"
DOCS_DIR = ROOT / "docs"


# ── JIRA Helpers ──────────────────────────────────────────────────────────────

def _jira_auth_header() -> str:
    email = os.environ.get("ATLASSIAN_EMAIL", "")
    token = os.environ.get("ATLASSIAN_API_TOKEN", "")
    if not email or not token:
        return ""
    return base64.b64encode(f"{email}:{token}".encode()).decode()


def _jira_domain() -> str:
    return os.environ.get("ATLASSIAN_DOMAIN", "datadoghq.atlassian.net")


def _jira_get(endpoint: str) -> dict:
    auth = _jira_auth_header()
    if not auth:
        return {"error": "JIRA credentials not configured. Need ATLASSIAN_EMAIL and ATLASSIAN_API_TOKEN in .env"}
    url = f"https://{_jira_domain()}/rest/api/3/{endpoint}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Basic {auth}",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return {"error": f"JIRA API error {e.code}: {e.reason}"}
    except Exception as e:
        return {"error": f"JIRA connection failed: {e}"}


def _extract_adf_text(node) -> str:
    """Extract plain text from Atlassian Document Format."""
    if not node:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, dict):
        if node.get("type") == "text":
            return node.get("text", "")
        if "content" in node:
            return "".join(_extract_adf_text(c) for c in node["content"])
    if isinstance(node, list):
        return "".join(_extract_adf_text(c) for c in node)
    return ""


# ── Tool Functions ────────────────────────────────────────────────────────────

def search_workspace(query: str) -> str:
    """Search through all local investigation notes, archived tickets, and
    documentation files for relevant content. Returns matching excerpts with
    file paths. Use this when looking for patterns, past investigations, or
    specific topics across the workspace.

    Args:
        query: Keywords to search for across all local markdown files.
    """
    results = []
    query_lower = query.lower()
    search_dirs = [INVESTIGATIONS_DIR, ARCHIVE_DIR, DOCS_DIR]

    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        for md_file in search_dir.rglob("*.md"):
            if md_file.name.startswith("."):
                continue
            try:
                content = md_file.read_text(encoding="utf-8")
            except Exception:
                continue
            if query_lower not in content.lower():
                continue

            title_match = re.match(r"^#\s+(.+)", content, re.MULTILINE)
            title = title_match.group(1).strip() if title_match else md_file.stem

            lines = content.split("\n")
            snippets = []
            for i, line in enumerate(lines):
                if query_lower in line.lower():
                    start = max(0, i - 1)
                    end = min(len(lines), i + 2)
                    snippet = "\n".join(lines[start:end]).strip()
                    snippets.append(snippet)
                    if len(snippets) >= 2:
                        break

            rel = str(md_file.relative_to(ROOT))
            results.append(f"**{title}** ({rel}):\n" + "\n...\n".join(snippets))

            if len(results) >= 10:
                break

    if not results:
        return f"No local files found matching '{query}'."
    return "\n\n---\n\n".join(results)


def read_investigation(ticket_key: str) -> str:
    """Read the full contents of a local investigation or archived ticket.
    Checks both the active investigations folder and the archive.
    Use when the user asks about a specific SCRS ticket.

    Args:
        ticket_key: The SCRS ticket key, e.g. 'SCRS-1930'.
    """
    # Check investigations/
    inv_dir = INVESTIGATIONS_DIR / ticket_key
    if inv_dir.exists() and inv_dir.is_dir():
        parts = []
        for md_file in sorted(inv_dir.glob("*.md")):
            try:
                content = md_file.read_text(encoding="utf-8")
                parts.append(f"=== {md_file.name} ===\n{content}")
            except Exception:
                continue
        if parts:
            return "\n\n".join(parts)

    # Check archive/
    if ARCHIVE_DIR.exists():
        for month_dir in ARCHIVE_DIR.iterdir():
            if not month_dir.is_dir():
                continue
            ticket_file = month_dir / f"{ticket_key}.md"
            if ticket_file.exists():
                try:
                    return ticket_file.read_text(encoding="utf-8")
                except Exception:
                    pass

    return f"No local investigation or archived ticket found for {ticket_key}."


def fetch_jira_ticket(ticket_key: str) -> str:
    """Fetch a JIRA ticket's live data including metadata, description, and
    comments. Use when you need the latest ticket information from JIRA,
    especially for tickets that may not have local investigation files yet.

    Args:
        ticket_key: The JIRA ticket key, e.g. 'SCRS-1930'.
    """
    data = _jira_get(f"issue/{ticket_key}")
    if "error" in data:
        return data["error"]

    fields = data.get("fields", {})
    key = data.get("key", ticket_key)
    summary = fields.get("summary", "No summary")
    status = fields.get("status", {}).get("name", "Unknown")
    priority = fields.get("priority", {}).get("name", "Unknown")
    created = fields.get("created", "")[:10]
    updated = fields.get("updated", "")[:10]

    reporter = fields.get("reporter", {})
    reporter_name = reporter.get("displayName", "Unknown") if reporter else "Unknown"

    labels = fields.get("labels", [])
    description = _extract_adf_text(fields.get("description", {}))

    # Comments (last 10)
    comments_data = fields.get("comment", {}).get("comments", [])
    comments = []
    for c in comments_data[-10:]:
        author = c.get("author", {}).get("displayName", "Unknown")
        created_at = c.get("created", "")[:10]
        body = _extract_adf_text(c.get("body", {}))
        if body.strip():
            comments.append(f"[{author} on {created_at}]: {body[:500]}")

    result = f"""**{key}: {summary}**
Status: {status} | Priority: {priority}
Reporter: {reporter_name} | Created: {created} | Updated: {updated}
Labels: {', '.join(labels) if labels else 'None'}

**Description:**
{description[:3000]}

**Comments ({len(comments_data)} total, showing last {len(comments)}):**
{chr(10).join(comments) if comments else 'No comments'}"""

    return result


def search_jira(jql_query: str) -> str:
    """Search JIRA tickets using JQL (JIRA Query Language). Always scope
    queries to project = SCRS unless the user explicitly asks about another
    project.

    Args:
        jql_query: A JQL query string, e.g. 'project = SCRS AND status != Done ORDER BY updated DESC'.
    """
    auth = _jira_auth_header()
    if not auth:
        return "JIRA credentials not configured. Need ATLASSIAN_EMAIL and ATLASSIAN_API_TOKEN in .env"

    encoded_jql = urllib.parse.quote(jql_query)
    fields = "summary,status,priority,created,updated,assignee,labels"
    url = (
        f"https://{_jira_domain()}/rest/api/3/search/jql"
        f"?jql={encoded_jql}&maxResults=20&fields={fields}"
    )

    req = urllib.request.Request(url, headers={
        "Authorization": f"Basic {auth}",
        "Accept": "application/json",
    })

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return f"JIRA search error {e.code}: {e.reason}"
    except Exception as e:
        return f"JIRA connection failed: {e}"

    issues = data.get("issues", [])
    if not issues:
        return f"No JIRA tickets found for query: {jql_query}"

    results = []
    for issue in issues:
        key = issue.get("key")
        f = issue.get("fields", {})
        summary = f.get("summary", "")
        status = f.get("status", {}).get("name", "")
        priority = f.get("priority", {}).get("name", "")
        updated = f.get("updated", "")[:10]
        labels_list = f.get("labels", [])
        results.append(
            f"- **{key}**: {summary} [{status}] "
            f"(Priority: {priority}, Updated: {updated}"
            f"{', Labels: ' + ', '.join(labels_list) if labels_list else ''})"
        )

    total = data.get("total", len(issues))
    header = f"Found {total} tickets (showing {len(issues)}):\n"
    return header + "\n".join(results)


# ── Registry ──────────────────────────────────────────────────────────────────

TOOL_FUNCTIONS = {
    "search_workspace": search_workspace,
    "read_investigation": read_investigation,
    "fetch_jira_ticket": fetch_jira_ticket,
    "search_jira": search_jira,
}

# Human-readable descriptions for UI tool indicators
TOOL_UI_LABELS = {
    "search_workspace": "Searching local files",
    "read_investigation": "Reading investigation",
    "fetch_jira_ticket": "Fetching JIRA ticket",
    "search_jira": "Searching JIRA",
}

# Pass these directly to Gemini's GenerativeModel(tools=[...])
ALL_TOOL_FUNCTIONS = [
    search_workspace,
    read_investigation,
    fetch_jira_ticket,
    search_jira,
]

