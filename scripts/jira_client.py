#!/usr/bin/env python3
"""
JIRA Client for Security TEE Hub

Utility for querying and archiving JIRA tickets from the SCRS project.
Reads credentials from ../.env file.

Usage:
    python jira_client.py get SCRS-1885           # Get single issue
    python jira_client.py search "status = Open"  # Search with JQL
    python jira_client.py archive SCRS-1885       # Archive to ../archive/
"""

import os
import sys
import json
import base64
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path
from datetime import datetime

# Load environment from .env
def load_env():
    env_path = Path(__file__).parent.parent / ".env"
    if not env_path.exists():
        print(f"Error: .env file not found at {env_path}")
        sys.exit(1)
    
    env = {}
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                env[key.strip()] = value.strip()
    return env

ENV = load_env()
DOMAIN = ENV.get("ATLASSIAN_DOMAIN", "datadoghq.atlassian.net")
EMAIL = ENV.get("ATLASSIAN_EMAIL")
TOKEN = ENV.get("ATLASSIAN_API_TOKEN")
PROJECT = ENV.get("JIRA_PROJECT_KEY", "SCRS")

def make_request(endpoint: str) -> dict:
    """Make authenticated request to JIRA API."""
    url = f"https://{DOMAIN}/rest/api/3/{endpoint}"
    
    # Basic auth: email:token base64 encoded
    credentials = base64.b64encode(f"{EMAIL}:{TOKEN}".encode()).decode()
    
    req = urllib.request.Request(url, headers={
        "Authorization": f"Basic {credentials}",
        "Accept": "application/json"
    })
    
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        print(f"HTTP Error {e.code}: {e.reason}")
        sys.exit(1)

def get_issue(issue_key: str) -> dict:
    """Fetch a single JIRA issue."""
    return make_request(f"issue/{issue_key}")

def search_issues(jql: str, max_results: int = 50) -> list:
    """Search issues with JQL using the new API v3 search endpoint."""
    # New API endpoint as of 2025 - need to specify fields explicitly
    encoded_jql = urllib.parse.quote(jql)
    fields = "summary,status,priority,created,updated,assignee"
    url = f"https://{DOMAIN}/rest/api/3/search/jql?jql={encoded_jql}&maxResults={max_results}&fields={fields}"
    
    credentials = base64.b64encode(f"{EMAIL}:{TOKEN}".encode()).decode()
    
    req = urllib.request.Request(url, headers={
        "Authorization": f"Basic {credentials}",
        "Accept": "application/json"
    })
    
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            return data.get("issues", [])
    except urllib.error.HTTPError as e:
        print(f"HTTP Error {e.code}: {e.reason}")
        return []

def extract_text(adf_content: dict) -> str:
    """Extract plain text from Atlassian Document Format."""
    if not adf_content:
        return ""
    
    def extract_node(node):
        if isinstance(node, str):
            return node
        if isinstance(node, dict):
            if node.get("type") == "text":
                return node.get("text", "")
            if "content" in node:
                return "".join(extract_node(c) for c in node["content"])
        if isinstance(node, list):
            return "".join(extract_node(c) for c in node)
        return ""
    
    return extract_node(adf_content)

def format_issue_markdown(issue: dict) -> str:
    """Convert JIRA issue to markdown format."""
    fields = issue.get("fields", {})
    
    # Extract key fields
    key = issue.get("key", "UNKNOWN")
    summary = fields.get("summary", "No summary")
    status = fields.get("status", {}).get("name", "Unknown")
    priority = fields.get("priority", {}).get("name", "Unknown")
    created = fields.get("created", "")[:10]
    updated = fields.get("updated", "")[:10]
    
    # Reporter and assignee
    reporter = fields.get("reporter", {})
    reporter_name = reporter.get("displayName", "Unknown") if reporter else "Unknown"
    
    assignees = fields.get("customfield_11300", []) or []
    assignee_names = [a.get("displayName", "Unknown") for a in assignees] if assignees else ["Unassigned"]
    
    # Customer info
    customer = fields.get("customfield_10237", "Unknown")
    
    # Description
    description = extract_text(fields.get("description", {}))
    
    # Comments
    comments_data = fields.get("comment", {}).get("comments", [])
    comments = []
    for c in comments_data:
        author = c.get("author", {}).get("displayName", "Unknown")
        created_at = c.get("created", "")[:10]
        body = extract_text(c.get("body", {}))
        comments.append(f"### {author} ({created_at})\n{body}")
    
    # Labels
    labels = fields.get("labels", [])
    
    md = f"""# {key}: {summary}

## Metadata
| Field | Value |
|-------|-------|
| **Status** | {status} |
| **Priority** | {priority} |
| **Customer** | {customer} |
| **Reporter** | {reporter_name} |
| **Assignees** | {', '.join(assignee_names)} |
| **Created** | {created} |
| **Updated** | {updated} |
| **Labels** | {', '.join(labels) if labels else 'None'} |

## Description
{description}

## Comments
{'---'.join(comments) if comments else 'No comments'}

---
*Archived: {datetime.now().isoformat()}*
"""
    return md

def archive_issue(issue_key: str):
    """Fetch issue and save to archive folder, organized by MM-YYYY."""
    archive_dir = Path(__file__).parent.parent / "archive"
    archive_dir.mkdir(exist_ok=True)
    
    print(f"Fetching {issue_key}...")
    issue = get_issue(issue_key)
    
    # Get created date for folder organization
    created = issue.get("fields", {}).get("created", "")
    if created and len(created) >= 10:
        # Format: 2026-01-22T... → 01-2026
        year = created[0:4]
        month = created[5:7]
        folder_name = f"{month}-{year}"
    else:
        folder_name = "unknown"
    
    # Create month folder if needed
    month_folder = archive_dir / folder_name
    month_folder.mkdir(parents=True, exist_ok=True)
    
    md = format_issue_markdown(issue)
    
    output_path = month_folder / f"{issue_key}.md"
    with open(output_path, "w") as f:
        f.write(md)
    
    print(f"Archived to {output_path}")

def main():
    import urllib.parse
    
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    command = sys.argv[1].lower()
    
    if command == "get" and len(sys.argv) >= 3:
        issue = get_issue(sys.argv[2])
        print(format_issue_markdown(issue))
    
    elif command == "search" and len(sys.argv) >= 3:
        jql = sys.argv[2]
        issues = search_issues(jql)
        for issue in issues:
            key = issue.get("key")
            summary = issue.get("fields", {}).get("summary", "")
            status = issue.get("fields", {}).get("status", {}).get("name", "")
            print(f"{key}: {summary} [{status}]")
    
    elif command == "archive" and len(sys.argv) >= 3:
        archive_issue(sys.argv[2])
    
    elif command == "list-open":
        jql = f"project = {PROJECT} AND status != Done AND status != Closed ORDER BY updated DESC"
        issues = search_issues(jql)
        for issue in issues:
            key = issue.get("key")
            summary = issue.get("fields", {}).get("summary", "")[:60]
            status = issue.get("fields", {}).get("status", {}).get("name", "")
            print(f"{key}: {summary}... [{status}]")
    
    else:
        print(__doc__)
        sys.exit(1)

if __name__ == "__main__":
    main()

