#!/usr/bin/env python3
"""
Bulk archive SCRS tickets from the last N days.

Usage:
    python bulk_archive.py              # Last 90 days (default)
    python bulk_archive.py --days 30    # Last 30 days
    python bulk_archive.py --all        # All tickets (careful!)
"""

import os
import sys
import json
import base64
import urllib.request
import urllib.parse
import time
from pathlib import Path
from datetime import datetime, timedelta

# Load environment
def load_env():
    env_path = Path(__file__).parent.parent / ".env"
    env = {}
    if env_path.exists():
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
ARCHIVE_DIR = Path(__file__).parent.parent / "archive"

def get_auth_header():
    credentials = base64.b64encode(f"{EMAIL}:{TOKEN}".encode()).decode()
    return f"Basic {credentials}"

def search_issues(jql: str, max_results: int = 100) -> list:
    """Search issues with JQL using nextPageToken pagination."""
    encoded_jql = urllib.parse.quote(jql)
    all_issues = []
    next_token = None
    
    while len(all_issues) < max_results:
        batch_size = min(100, max_results - len(all_issues))
        url = f"https://{DOMAIN}/rest/api/3/search/jql?jql={encoded_jql}&maxResults={batch_size}&fields=key,summary,status,created"
        if next_token:
            url += f"&nextPageToken={urllib.parse.quote(next_token)}"
        
        req = urllib.request.Request(url, headers={
            "Authorization": get_auth_header(),
            "Accept": "application/json"
        })
        
        try:
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode())
                issues = data.get("issues", [])
                all_issues.extend(issues)
                
                # Check if there are more pages
                if data.get("isLast", True) or not issues:
                    break
                    
                next_token = data.get("nextPageToken")
                if not next_token:
                    break
                    
                print(f"  Fetched {len(all_issues)} issues so far...")
        except urllib.error.HTTPError as e:
            print(f"HTTP Error {e.code}: {e.reason}")
            break
    
    return all_issues

def get_issue(issue_key: str) -> dict:
    """Fetch a single issue with all fields."""
    url = f"https://{DOMAIN}/rest/api/3/issue/{issue_key}"
    
    req = urllib.request.Request(url, headers={
        "Authorization": get_auth_header(),
        "Accept": "application/json"
    })
    
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode())

def extract_text(adf_content) -> str:
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
    
    key = issue.get("key", "UNKNOWN")
    summary = fields.get("summary", "No summary")
    status = fields.get("status", {}).get("name", "Unknown")
    priority = fields.get("priority", {}).get("name", "Unknown") if fields.get("priority") else "Unknown"
    created = fields.get("created", "")[:10]
    updated = fields.get("updated", "")[:10]
    
    reporter = fields.get("reporter", {})
    reporter_name = reporter.get("displayName", "Unknown") if reporter else "Unknown"
    
    assignees = fields.get("customfield_11300", []) or []
    assignee_names = [a.get("displayName", "Unknown") for a in assignees] if assignees else ["Unassigned"]
    
    customer = fields.get("customfield_10237", "Unknown")
    description = extract_text(fields.get("description", {}))
    
    comments_data = fields.get("comment", {}).get("comments", [])
    comments = []
    for c in comments_data:
        author = c.get("author", {}).get("displayName", "Unknown")
        created_at = c.get("created", "")[:10]
        body = extract_text(c.get("body", {}))
        comments.append(f"### {author} ({created_at})\n{body}")
    
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
{chr(10).join(comments) if comments else 'No comments'}

---
*Archived: {datetime.now().isoformat()}*
"""
    return md

def archive_issue(issue_key: str) -> bool:
    """Fetch and archive a single issue, organized by MM-YYYY folder."""
    try:
        issue = get_issue(issue_key)
        md = format_issue_markdown(issue)
        
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
        month_folder = ARCHIVE_DIR / folder_name
        month_folder.mkdir(parents=True, exist_ok=True)
        
        output_path = month_folder / f"{issue_key}.md"
        with open(output_path, "w") as f:
            f.write(md)
        return True
    except Exception as e:
        print(f"  Error archiving {issue_key}: {e}")
        return False

def count_issues(jql: str) -> int:
    """Count issues matching JQL by paginating through results (lightweight)."""
    encoded_jql = urllib.parse.quote(jql)
    count = 0
    next_token = None
    max_pages = 20  # Safety: don't check more than 20 pages (2000 issues)
    
    try:
        for page in range(max_pages):
            url = f"https://{DOMAIN}/rest/api/3/search/jql?jql={encoded_jql}&maxResults=100&fields=key"
            if next_token:
                url += f"&nextPageToken={urllib.parse.quote(next_token)}"
            
            req = urllib.request.Request(url, headers={
                "Authorization": get_auth_header(),
                "Accept": "application/json"
            })
            
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode())
                issues = data.get("issues", [])
                count += len(issues)
                
                if data.get("isLast", True) or not issues:
                    return count
                
                next_token = data.get("nextPageToken")
                if not next_token:
                    return count
                
                print(f"  Counting... {count} so far")
        
        # Hit max pages
        print(f"  ⚠️  More than {count} tickets (stopped counting at page {max_pages})")
        return count
        
    except Exception as e:
        print(f"Error counting issues: {e}")
        return -1

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Bulk archive SCRS tickets")
    parser.add_argument("--days", type=int, default=90, help="Number of days to look back")
    parser.add_argument("--all", action="store_true", help="Archive all tickets")
    parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")
    parser.add_argument("--limit", type=int, default=500, help="Max tickets to archive (safety limit)")
    args = parser.parse_args()
    
    ARCHIVE_DIR.mkdir(exist_ok=True)
    
    # Build JQL
    if args.all:
        jql = f"project = {PROJECT} ORDER BY created DESC"
        print(f"Querying ALL {PROJECT} tickets...")
    else:
        # Use relative date syntax which works better with the new API
        jql = f"project = {PROJECT} AND created >= -{args.days}d ORDER BY created DESC"
        print(f"Querying {PROJECT} tickets from last {args.days} days...")
    
    # === SAFETY CHECK ===
    print("Checking ticket count first...")
    estimated_count = count_issues(jql)
    
    if estimated_count < 0:
        print("❌ Could not determine ticket count. Aborting for safety.")
        return
    
    print(f"\n📊 Estimated tickets: ~{estimated_count}")
    
    # Safety limit check
    if estimated_count > args.limit:
        print(f"\n⚠️  WARNING: This exceeds the safety limit of {args.limit} tickets!")
        print(f"   Use --limit {estimated_count} to override, or narrow your search.")
        print(f"   Example: python bulk_archive.py --days 90 --limit {estimated_count} --yes")
        print("\nAborted for safety.")
        return
    
    # Reasonable count - proceed (auto-confirm in non-interactive mode)
    if not args.yes:
        print(f"\nThis will archive ~{estimated_count} tickets to {ARCHIVE_DIR}")
        try:
            response = input("Proceed? [Y/n]: ").strip().lower()
            if response == 'n':
                print("Aborted.")
                return
        except EOFError:
            # Non-interactive mode - proceed if under limit
            print("(Non-interactive mode - proceeding automatically)")
    
    print(f"\n✅ Proceeding with archive (limit: {args.limit})...\n")
    
    # Search for issues (with limit)
    issues = search_issues(jql, max_results=min(100, args.limit))
    
    # Apply limit
    if len(issues) > args.limit:
        print(f"⚠️  Limiting to {args.limit} tickets (found {len(issues)})")
        issues = issues[:args.limit]
    
    print(f"Found {len(issues)} tickets to archive")
    
    if not issues:
        print("No issues found.")
        return
    
    # Archive each issue
    success = 0
    failed = 0
    
    for i, issue in enumerate(issues):
        key = issue.get("key")
        summary = issue.get("fields", {}).get("summary", "")[:50]
        print(f"[{i+1}/{len(issues)}] Archiving {key}: {summary}...")
        
        if archive_issue(key):
            success += 1
        else:
            failed += 1
        
        # Rate limiting - be nice to the API
        time.sleep(0.2)
    
    print(f"\nDone! Archived {success} tickets, {failed} failed")
    print(f"Archive location: {ARCHIVE_DIR}")

if __name__ == "__main__":
    main()

