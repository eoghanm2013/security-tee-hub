#!/usr/bin/env python3
"""
Security TEE Hub - Automated Setup

Configures .cursor/mcp.json with MCP servers (Atlassian via SSO, Glean via SSO,
GitHub via PAT). Atlassian and Glean use SSO URLs -- no tokens needed.

Usage:
    Interactive:  python3 scripts/setup.py
    With args:    python3 scripts/setup.py --github-token XXX
    Minimal:      python3 scripts/setup.py --skip-github
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

ATLASSIAN_MCP_URL = "https://mcp.atlassian.com/v1/mcp"
GLEAN_MCP_URL = "https://datadog-be.glean.com/mcp/default"
JIRA_PROJECT_KEY = "SCRS"


def prompt(msg: str, default: str = "", required: bool = True) -> str:
    suffix = f" [{default}]" if default else ""
    while True:
        value = input(f"{msg}{suffix}: ").strip()
        if not value and default:
            return default
        if value:
            return value
        if not required:
            return ""
        print("  This field is required.")


def check_uv() -> bool:
    return shutil.which("uvx") is not None or shutil.which("uv") is not None


def install_uv() -> bool:
    print("\nInstalling uv...")
    try:
        subprocess.run(
            ["sh", "-c", "curl -LsSf https://astral.sh/uv/install.sh | sh"],
            check=True,
        )
        print("uv installed successfully.")
        return True
    except subprocess.CalledProcessError:
        print("Failed to install uv. Install manually: https://docs.astral.sh/uv/getting-started/installation/")
        return False


def write_mcp_json(github_token: str = "") -> Path:
    cursor_dir = ROOT_DIR / ".cursor"
    cursor_dir.mkdir(exist_ok=True)
    mcp_path = cursor_dir / "mcp.json"

    config: dict = {"mcpServers": {}}

    config["mcpServers"]["atlassian"] = {
        "url": ATLASSIAN_MCP_URL,
    }

    config["mcpServers"]["glean_default"] = {
        "url": GLEAN_MCP_URL,
    }

    if github_token:
        config["mcpServers"]["github"] = {
            "command": "uvx",
            "args": ["mcp-github"],
            "env": {"GITHUB_TOKEN": github_token},
        }

    mcp_path.write_text(json.dumps(config, indent=2) + "\n")
    return mcp_path


def write_env(github_token: str = "") -> Path:
    env_path = ROOT_DIR / ".env"

    lines = [
        "# JIRA Project Configuration",
        f"JIRA_PROJECT_KEY={JIRA_PROJECT_KEY}",
        "",
        "# GitHub Configuration (optional)",
        f"GITHUB_TOKEN={github_token}" if github_token else "# GITHUB_TOKEN=",
    ]

    env_path.write_text("\n".join(lines) + "\n")
    return env_path


def ensure_directories():
    for name in ["investigations", "archive"]:
        d = ROOT_DIR / name
        d.mkdir(exist_ok=True)


def main():
    parser = argparse.ArgumentParser(description="Security TEE Hub Setup")
    parser.add_argument("--github-token", default="", help="GitHub PAT (optional)")
    parser.add_argument("--skip-github", action="store_true", help="Skip GitHub setup")
    parser.add_argument("--reconfigure", action="store_true", help="Overwrite existing config files")
    args = parser.parse_args()

    print("=" * 50)
    print("  Security TEE Hub - Setup")
    print("=" * 50)

    mcp_path = ROOT_DIR / ".cursor" / "mcp.json"

    if mcp_path.exists() and not args.reconfigure:
        if not args.github_token and not args.skip_github:
            resp = input("\n.cursor/mcp.json already exists. Overwrite? [y/N]: ").strip().lower()
            if resp != "y":
                print("Setup cancelled. Use --reconfigure to force.")
                sys.exit(0)

    github_token = args.github_token
    if not github_token and not args.skip_github:
        print("\nAtlassian and Glean use SSO -- no tokens needed.")
        print("GitHub requires a Personal Access Token (optional).\n")
        github_token = prompt("GitHub PAT (Enter to skip)", required=False)

    print("\nWriting .cursor/mcp.json ...")
    write_mcp_json(github_token)
    print(f"  -> {mcp_path}")

    print("Writing .env ...")
    env_path = write_env(github_token)
    print(f"  -> {env_path}")

    ensure_directories()

    if github_token and not check_uv():
        print("\nuv/uvx not found (needed for GitHub MCP server).")
        resp = input("Install uv now? [Y/n]: ").strip().lower()
        if resp != "n":
            install_uv()
        else:
            print("Skipped. Install later: curl -LsSf https://astral.sh/uv/install.sh | sh")
    elif github_token:
        print("\nuv/uvx found.")

    print("\n" + "=" * 50)
    print("  Setup complete!")
    print("=" * 50)
    print()
    print("Next steps:")
    print("  1. Restart Cursor (Cmd+Q, then reopen)")
    print("  2. Atlassian and Glean will prompt SSO login on first use")
    if github_token:
        print("  3. Test: \"Use MCP to fetch JIRA ticket SCRS-1885\"")
    else:
        print("  3. Test: \"Use MCP to fetch JIRA ticket SCRS-1885\"")
        print("     (GitHub skipped -- add later with --reconfigure)")
    print()


if __name__ == "__main__":
    main()
