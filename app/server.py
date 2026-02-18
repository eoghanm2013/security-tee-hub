#!/usr/bin/env python3
"""
TEE Hub - Local web interface for Security TEE investigations.

Usage:
    python server.py              # Start on http://localhost:5001
    python server.py --port 8080  # Custom port
"""

import os
import re
import sys
import json
import time
import threading
from pathlib import Path
from datetime import datetime

from flask import Flask, render_template, request, jsonify, abort, Response, stream_with_context

import markdown
from markdown.extensions.codehilite import CodeHiliteExtension
from markdown.extensions.fenced_code import FencedCodeExtension
from markdown.extensions.tables import TableExtension
from markdown.extensions.toc import TocExtension

# ── Paths ────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent.parent
INVESTIGATIONS_DIR = ROOT / "investigations"
ARCHIVE_DIR = ROOT / "archive"
DOCS_DIR = ROOT / "docs"


# ── File Watcher (live-reload for investigation pages) ───────────────────────

# Maps investigation key -> timestamp of last change (float, time.time())
# Special key "_list" tracks directory-level changes (new/deleted investigations)
_investigation_changes: dict[str, float] = {}
_investigation_changes_lock = threading.Lock()


def _start_file_watcher():
    """Start a background thread that watches investigations/ for file changes."""
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
    except ImportError:
        print("[live-reload] watchdog not installed, skipping file watcher")
        return

    class _InvestigationHandler(FileSystemEventHandler):
        def _handle(self, event):
            path = Path(event.src_path)
            try:
                rel = path.relative_to(INVESTIGATIONS_DIR)
            except ValueError:
                return

            # Directory created/deleted at top level = new or removed investigation
            if event.is_directory and len(rel.parts) == 1:
                inv_key = rel.parts[0]
                if not inv_key.startswith("."):
                    now = time.time()
                    with _investigation_changes_lock:
                        _investigation_changes["_list"] = now
                        _investigation_changes[inv_key] = now
                return

            # File changes within an investigation folder
            if event.is_directory:
                return
            inv_key = rel.parts[0] if rel.parts else None
            if inv_key and not inv_key.startswith("."):
                with _investigation_changes_lock:
                    _investigation_changes[inv_key] = time.time()

        def on_modified(self, event):
            self._handle(event)

        def on_created(self, event):
            self._handle(event)

        def on_deleted(self, event):
            self._handle(event)

    observer = Observer()
    observer.schedule(_InvestigationHandler(), str(INVESTIGATIONS_DIR), recursive=True)
    observer.daemon = True
    observer.start()
    print(f"[live-reload] Watching {INVESTIGATIONS_DIR} for changes")


# ── Environment / API Keys ───────────────────────────────────────────────────

def _load_env_file():
    """Load variables from .env file if present."""
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                key, value = key.strip(), value.strip()
                if key not in os.environ:
                    os.environ[key] = value

_load_env_file()

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "")  # auto-detect if empty


def _load_system_prompt():
    """Load .cursorrules as the system prompt for the chat."""
    rules_path = ROOT / ".cursorrules"
    if rules_path.exists():
        return rules_path.read_text(encoding="utf-8")
    return (
        "You are a helpful assistant for Technical Escalation Engineers (TEEs) "
        "on Datadog's Security Products team. Help investigate JIRA tickets, "
        "assess escalation quality, search for patterns, and draft responses."
    )


SYSTEM_PROMPT = _load_system_prompt()


# ── Chat Provider Detection ──────────────────────────────────────────────────

import urllib.request
import urllib.error


def _check_ollama() -> dict:
    """Check if Ollama is running and what models are available."""
    try:
        req = urllib.request.Request(
            f"{OLLAMA_BASE_URL}/api/tags",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read().decode())
            models = [m["name"] for m in data.get("models", [])]
            return {"running": True, "models": models}
    except Exception:
        return {"running": False, "models": []}


def _pick_ollama_model(available: list) -> str:
    """Pick the best available Ollama model for TEE work."""
    if OLLAMA_MODEL and OLLAMA_MODEL in available:
        return OLLAMA_MODEL
    if OLLAMA_MODEL:
        # Try partial match (e.g. "llama3.1" matches "llama3.1:latest")
        for m in available:
            if OLLAMA_MODEL in m:
                return m
    # Preference order: reasoning-capable models first
    preferred = [
        "qwen2.5:14b", "qwen2.5:7b", "qwen2.5",
        "llama3.1:8b", "llama3.1", "llama3:8b", "llama3",
        "mistral", "mistral:7b",
        "gemma2:9b", "gemma2",
        "phi3:medium", "phi3",
        "deepseek-r1:8b", "deepseek-r1",
    ]
    for p in preferred:
        for m in available:
            if p in m:
                return m
    # Just use the first available model
    return available[0] if available else ""


def get_chat_provider() -> dict:
    """Determine which chat provider is available. Priority: Anthropic > Gemini > Ollama."""
    if ANTHROPIC_API_KEY:
        return {
            "provider": "anthropic",
            "model": "claude-sonnet-4-20250514",
            "label": "Claude (Anthropic)",
            "available": True,
            "has_tools": False,
        }

    if GEMINI_API_KEY:
        return {
            "provider": "gemini",
            "model": GEMINI_MODEL,
            "label": f"{GEMINI_MODEL} (Gemini)",
            "available": True,
            "has_tools": True,
        }

    ollama = _check_ollama()
    if ollama["running"] and ollama["models"]:
        model = _pick_ollama_model(ollama["models"])
        if model:
            return {
                "provider": "ollama",
                "model": model,
                "label": f"{model} (Ollama)",
                "available": True,
                "has_tools": False,
                "all_models": ollama["models"],
            }
        return {
            "provider": "ollama",
            "model": "",
            "label": "Ollama (no models)",
            "available": False,
            "has_tools": False,
            "all_models": [],
        }

    return {"provider": "none", "model": "", "label": "", "available": False, "has_tools": False}

# ── Flask App ────────────────────────────────────────────────────────────────

app = Flask(
    __name__,
    template_folder=str(Path(__file__).parent / "templates"),
    static_folder=str(Path(__file__).parent / "static"),
)


@app.context_processor
def inject_globals():
    """Make chat availability and current page info available to all templates."""
    provider = get_chat_provider()
    inv_count = len(get_investigations())
    archive_months = get_archive_months()
    return {
        "chat_available": provider["available"],
        "chat_provider_label": provider.get("label", ""),
        "nav_investigation_count": inv_count,
        "nav_archive_count": sum(m["count"] for m in archive_months),
        "nav_doc_count": len(list(DOCS_DIR.rglob("*.md"))) if DOCS_DIR.exists() else 0,
    }


# ── Helpers ──────────────────────────────────────────────────────────────────

def render_md(text: str) -> str:
    """Render markdown to HTML with syntax highlighting and tables."""
    extensions = [
        FencedCodeExtension(),
        CodeHiliteExtension(css_class="codehilite", guess_lang=False),
        TableExtension(),
        TocExtension(permalink=False),
        "nl2br",
    ]
    return markdown.markdown(text, extensions=extensions)


def read_md_file(path: Path) -> dict:
    """Read a markdown file and return metadata + rendered HTML."""
    if not path.exists():
        return None
    raw = path.read_text(encoding="utf-8")
    # Try to extract a title from the first # heading
    title_match = re.match(r"^#\s+(.+)", raw, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else path.stem
    return {
        "title": title,
        "raw": raw,
        "html": render_md(raw),
        "path": str(path.relative_to(ROOT)),
        "modified": datetime.fromtimestamp(path.stat().st_mtime),
    }


VALID_STATUSES = ["investigating", "waiting", "escalated", "done"]
STATUS_LABELS = {
    "investigating": "Investigating",
    "waiting": "Waiting",
    "escalated": "Escalated",
    "done": "Done",
}


def _read_meta(inv_dir: Path) -> dict:
    """Read meta.json from an investigation folder, returning defaults if missing."""
    meta_path = inv_dir / "meta.json"
    meta = {"status": "investigating", "assignee": ""}
    if meta_path.exists():
        try:
            with open(meta_path) as f:
                data = json.loads(f.read())
            if data.get("status") in VALID_STATUSES:
                meta["status"] = data["status"]
            if data.get("assignee"):
                meta["assignee"] = str(data["assignee"]).strip()
        except Exception:
            pass
    return meta


def _write_meta(inv_dir: Path, meta: dict):
    """Write meta.json to an investigation folder."""
    meta_path = inv_dir / "meta.json"
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)
        f.write("\n")


def get_investigations() -> list:
    """List all active investigations sorted by last modified (newest first)."""
    if not INVESTIGATIONS_DIR.exists():
        return []
    investigations = []
    for d in sorted(INVESTIGATIONS_DIR.iterdir(), reverse=True):
        if not d.is_dir() or d.name.startswith("."):
            continue
        ticket_key = d.name
        notes_path = d / "notes.md"
        response_path = d / "response.md"

        # Try to get title from notes.md first line
        title = ticket_key
        if notes_path.exists():
            first_line = notes_path.read_text(encoding="utf-8").split("\n")[0]
            heading = re.match(r"^#\s+(.+)", first_line)
            if heading:
                title = heading.group(1).strip()

        # Read metadata (status, assignee)
        meta = _read_meta(d)

        # Collect all .md files in the investigation
        md_files = sorted(d.glob("*.md"))
        file_names = [f.name for f in md_files]

        # Get modification time (most recent file)
        mod_times = [f.stat().st_mtime for f in d.rglob("*") if f.is_file()]
        last_modified = datetime.fromtimestamp(max(mod_times)) if mod_times else None

        # Detect product area from title + notes content
        area_text = title
        if notes_path.exists():
            try:
                area_text += " " + notes_path.read_text(encoding="utf-8", errors="ignore")[:2000]
            except Exception:
                pass
        product_area = detect_product_area(area_text)

        investigations.append({
            "key": ticket_key,
            "title": title,
            "has_notes": notes_path.exists(),
            "has_response": response_path.exists(),
            "files": file_names,
            "file_count": len(md_files),
            "last_modified": last_modified,
            "path": str(d.relative_to(ROOT)),
            "status": meta["status"],
            "assignee": meta["assignee"],
            "product_area": product_area,
        })

    # Sort by last modified, newest first
    investigations.sort(key=lambda x: x["last_modified"] or datetime.min, reverse=True)
    return investigations


# Product area taxonomy based on:
# https://datadoghq.atlassian.net/wiki/spaces/TS/pages/5213524529
#
# Groups:
#   Cloud Security  -> cspm, vm, ciem
#   Code Security   -> sast, sca, iast
#   Threat Mgmt     -> siem, workload_protection, aap

PRODUCT_AREA_GROUPS = {
    "cloud_security": {
        "label": "Cloud Security",
        "slack": "#support-cloud-security",
        "areas": ["cspm", "vm", "ciem"],
    },
    "code_security": {
        "label": "Code Security",
        "slack": "#support-code-security",
        "areas": ["sast", "sca", "iast"],
    },
    "threat_management": {
        "label": "Threat Management",
        "slack": "#support-security-threats",
        "areas": ["siem", "workload_protection", "aap"],
    },
}

PRODUCT_AREA_RULES = [
    # (area_key, display_label, group_key, keyword_patterns)
    # Order matters: first match wins. More specific patterns come first.

    # -- Threat Management --
    ("siem", "Cloud SIEM", "threat_management", [
        r"\bcloud\s*siem\b", r"\bsiem\b", r"\bdetection\s*rule", r"\bsecurity\s*signal",
        r"\bcontent\s*pack", r"\blog\s*detection", r"\bthreat\s*intel",
    ]),
    ("aap", "AAP", "threat_management", [
        r"\baap\b", r"\bappsec\b", r"\basm\b", r"\bwaf\b", r"\bapi\s*security\b",
        r"\bin[- ]app\s*waf\b", r"\bip\s*block", r"\bpasslist\b",
        r"\battack\s*attempt", r"\bapplication[- ]security\b",
        r"\bapp\s*(and|&)\s*api\s*protect", r"\bsecurity\s*trace",
        r"\bphp.*(helper|sidecar)\b", r"\b(sidecar|helper).*php\b",
        r"\bdd_appsec_enabled\b",
    ]),
    ("workload_protection", "Workload Protection", "threat_management", [
        r"\bworkload\s*protection\b", r"\bcws\b", r"\bcloud\s*workload\s*security\b",
        r"\bruntime\s*security\b", r"\bactive\s*protection\b",
        r"\bsystem[- ]probe\b", r"\bsecurity[- ]agent\b", r"\bfim\b",
        r"\brunc\b", r"\bsbom\b", r"\bagent\s*rule\b",
        r"\bdynamic\s*linker\b", r"\bebpf\b",
    ]),

    # -- Cloud Security --
    ("cspm", "CSPM", "cloud_security", [
        r"\bcspm\b", r"\bposture\s*management\b", r"\bmisconfiguration\b",
        r"\bcompliance\b", r"\bbenchmark\b", r"\bcloud\s*configuration\b",
        r"\bcloud\s*security.*config", r"\bcis\b", r"\bstig\b", r"\bdisa\b",
        r"\biac\s*finding", r"\bfindings?\s*search\b",
    ]),
    ("vm", "Vulnerability Mgmt", "cloud_security", [
        r"\bvulnerability\s*management\b", r"\bvulnerab", r"\bcve\b",
        r"\bagentless\s*scann", r"\bhost\s*vulnerabilit",
        r"\bcontainer\s*image\s*vulnerabilit",
        r"\bcvss\b", r"\bepss\b", r"\bcisa\s*kev\b",
    ]),
    ("ciem", "CIEM", "cloud_security", [
        r"\bciem\b", r"\bidentity\s*risk", r"\bentitlement\s*management\b",
        r"\biam\s*access\s*analy", r"\bprivilege\s*escalat",
        r"\bcross[- ]account\s*access\b", r"\bblast\s*radius\b",
        r"\bidentity\s*risks?\b",
    ]),

    # -- Code Security --
    ("sast", "SAST", "code_security", [
        r"\bsast\b", r"\bstatic\s*(application\s*security|analysis)\b",
        r"\bcode\s*security.*static\b", r"\bstatic\s*code\b",
        r"\bhosted\s*scanning\b",
    ]),
    ("sca", "SCA", "code_security", [
        r"\bsca\b", r"\bsoftware\s*composition\b", r"\bdependenc",
        r"\brepo.*scanning\b", r"\bdd_appsec_sca_enabled\b",
        r"\blicense\s*risk", r"\bpackage\s*manifest",
    ]),
    ("iast", "IAST", "code_security", [
        r"\biast\b", r"\binteractive\s*application\s*security\b",
        r"\bdd_iast_enabled\b", r"\btainted\s*data\b",
        r"\bsource.*sink\b", r"\bsink.*source\b",
    ]),

    ("other", "Other", None, []),  # fallback
]

# Pre-compile patterns for performance
_COMPILED_AREA_RULES = [
    (key, label, group, [re.compile(p, re.IGNORECASE) for p in patterns])
    for key, label, group, patterns in PRODUCT_AREA_RULES
]

PRODUCT_AREA_LABELS = {key: label for key, label, _group, _pats in PRODUCT_AREA_RULES}

# Reverse lookup: area_key -> group_key
AREA_TO_GROUP = {key: group for key, _label, group, _pats in PRODUCT_AREA_RULES if group}


def detect_product_area(text: str) -> str:
    """Detect the product area from ticket title + description text.

    Returns the area key (e.g. 'aap', 'siem', 'cspm'). Falls back to 'other'.
    """
    # Check for "Org Deletion" pattern early (common, always 'other')
    if re.search(r"org\s*deletion\s*request", text, re.IGNORECASE):
        return "other"

    for key, _label, _group, patterns in _COMPILED_AREA_RULES:
        if not patterns:
            continue
        for pat in patterns:
            if pat.search(text):
                return key
    return "other"


# ── Data Source Extraction ───────────────────────────────────────────────────

# Source type definitions: (key, label, icon, url_patterns, ref_patterns)
# url_patterns match links in markdown; ref_patterns match non-link references
_SOURCE_TYPES = [
    ("jira", "JIRA", "ticket", [
        re.compile(r"https?://datadoghq\.atlassian\.net/browse/([\w-]+)", re.IGNORECASE),
    ], [
        re.compile(r"\b(SCRS-\d+|ZD-\d+|SECENG-\d+)\b"),
    ]),
    ("confluence", "Confluence", "wiki", [
        re.compile(r"https?://datadoghq\.atlassian\.net/wiki/[\w/+.-]+", re.IGNORECASE),
    ], []),
    ("datadog_docs", "Datadog Docs", "docs", [
        re.compile(r"https?://docs\.datadoghq\.com/[\w/._?&#%-]+", re.IGNORECASE),
    ], []),
    ("github", "GitHub", "code", [
        re.compile(r"https?://github\.com/[\w.-]+/[\w.-]+[\w/._?&#%-]*", re.IGNORECASE),
    ], []),
    ("slack", "Slack", "chat", [
        re.compile(r"https?://dd\.(?:enterprise\.)?slack\.com/[\w/.-]+", re.IGNORECASE),
    ], [
        re.compile(r"#[\w_-]{2,}", re.IGNORECASE),
    ]),
    ("terraform", "Terraform", "infra", [
        re.compile(r"https?://registry\.terraform\.io/[\w/._?&#%-]+", re.IGNORECASE),
    ], []),
]


def extract_sources(raw_text: str) -> list:
    """Extract data source references from markdown text.

    Returns a list of dicts, one per source type that had hits:
    [
        {
            "key": "jira",
            "label": "JIRA",
            "icon": "ticket",
            "refs": [
                {"url": "https://...", "display": "ZD-2113228", "context": "Similar case about ..."},
                ...
            ]
        },
        ...
    ]
    """
    lines = raw_text.split("\n")
    sources = []

    for src_key, src_label, src_icon, url_patterns, ref_patterns in _SOURCE_TYPES:
        refs_seen = set()  # dedupe by (url_or_ref, display)
        refs = []

        # Scan for URL matches in markdown links: [text](url) and bare URLs
        for url_pat in url_patterns:
            for match in url_pat.finditer(raw_text):
                url = match.group(0).rstrip(")")
                # Try to get the display text from markdown link syntax
                display = url
                # Check for [text](url) pattern
                start = match.start()
                prefix = raw_text[max(0, start - 200):start]
                md_link = re.search(r"\[([^\]]+)\]\s*\($", prefix)
                if md_link:
                    display = md_link.group(1)
                # For JIRA links, extract the ticket key
                elif src_key == "jira" and match.lastindex and match.lastindex >= 1:
                    display = match.group(1)

                dedup_key = (url, display)
                if dedup_key in refs_seen:
                    continue
                refs_seen.add(dedup_key)

                # Get surrounding context (the line containing this match)
                context = _get_context_for_match(lines, match.group(0), raw_text)
                refs.append({
                    "url": url,
                    "display": display,
                    "context": context,
                })

        # Scan for non-link reference patterns (ticket keys, Slack channels)
        for ref_pat in ref_patterns:
            for match in ref_pat.finditer(raw_text):
                ref_text = match.group(0)
                # Skip if we already captured this as a URL reference
                if any(ref_text in r["display"] or ref_text in r["url"] for r in refs):
                    continue

                dedup_key = (ref_text, ref_text)
                if dedup_key in refs_seen:
                    continue
                refs_seen.add(dedup_key)

                # Build a URL where possible
                url = None
                if src_key == "jira":
                    url = f"https://datadoghq.atlassian.net/browse/{ref_text}"
                elif src_key == "slack" and ref_text.startswith("#"):
                    url = None  # can't link to a channel without ID

                context = _get_context_for_match(lines, ref_text, raw_text)
                refs.append({
                    "url": url,
                    "display": ref_text,
                    "context": context,
                })

        if refs:
            sources.append({
                "key": src_key,
                "label": src_label,
                "icon": src_icon,
                "refs": refs,
            })

    return sources


def _get_context_for_match(lines: list, needle: str, full_text: str) -> str:
    """Get a summary context line for a matched reference.

    Finds the first line containing the needle, cleans markdown syntax, and
    truncates to a reasonable length.
    """
    for line in lines:
        if needle in line:
            # Clean markdown syntax
            clean = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)  # [text](url) -> text
            clean = re.sub(r"[#*>`_~]", "", clean).strip()
            clean = re.sub(r"\s+", " ", clean)
            # Remove the needle itself to avoid redundancy
            clean = clean.replace(needle, "").strip(" -:,.")
            if len(clean) > 150:
                clean = clean[:147] + "..."
            return clean if clean else ""
    return ""


def get_archive_months() -> list:
    """List archive months with ticket counts and product-area tags."""
    if not ARCHIVE_DIR.exists():
        return []
    def _month_sort_key(d):
        """Parse MM-YYYY folder name into (year, month) for proper date sorting."""
        try:
            parts = d.name.split("-")
            return (int(parts[1]), int(parts[0]))
        except (IndexError, ValueError):
            return (0, 0)

    months = []
    for d in sorted(ARCHIVE_DIR.iterdir(), key=_month_sort_key, reverse=True):
        if not d.is_dir():
            continue
        tickets = sorted(d.glob("*.md"), reverse=True)
        ticket_list = []
        for t in tickets:
            # Extract title from first # heading
            title = t.stem
            # Read enough content to detect product area (title + description)
            content_preview = ""
            try:
                content_preview = t.read_text(encoding="utf-8", errors="ignore")[:2000]
                first_lines = content_preview.split("\n", 5)
                for line in first_lines:
                    heading = re.match(r"^#\s+(.+)", line)
                    if heading:
                        title = heading.group(1).strip()
                        break
            except Exception:
                pass
            area = detect_product_area(content_preview)
            ticket_list.append({
                "key": t.stem,
                "path": str(t.relative_to(ROOT)),
                "title": title,
                "product_area": area,
            })
        months.append({
            "name": d.name,
            "count": len(ticket_list),
            "tickets": ticket_list,
        })
    return months


def get_docs_tree(base_dir: Path = None, prefix: str = "") -> list:
    """Build a tree of documentation files."""
    if base_dir is None:
        base_dir = DOCS_DIR
    if not base_dir.exists():
        return []
    tree = []
    for item in sorted(base_dir.iterdir()):
        if item.name.startswith(".") or item.name.startswith("_"):
            continue
        if item.is_dir():
            children = get_docs_tree(item, prefix=f"{prefix}{item.name}/")
            if children:
                tree.append({
                    "type": "dir",
                    "name": item.name,
                    "children": children,
                })
        elif item.suffix == ".md":
            tree.append({
                "type": "file",
                "name": item.stem,
                "path": str(item.relative_to(ROOT)),
            })
    return tree


def search_files(query: str, max_results: int = 50) -> list:
    """Search all markdown files for a query string (case-insensitive)."""
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

            # Find matching lines for context
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

            # Get title
            title_match = re.match(r"^#\s+(.+)", content, re.MULTILINE)
            title = title_match.group(1).strip() if title_match else md_file.stem

            # Determine section
            rel = md_file.relative_to(ROOT)
            section = str(rel).split("/")[0]

            results.append({
                "title": title,
                "path": str(rel),
                "section": section,
                "snippets": snippets,
                "modified": datetime.fromtimestamp(md_file.stat().st_mtime),
            })

            if len(results) >= max_results:
                return results

    # Sort by modification time (newest first)
    results.sort(key=lambda r: r["modified"], reverse=True)
    return results


# ── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def dashboard():
    investigations = get_investigations()
    archive_months = get_archive_months()
    total_archived = sum(m["count"] for m in archive_months)
    return render_template(
        "dashboard.html",
        investigations=investigations,
        archive_months=archive_months,
        total_archived=total_archived,
    )


@app.route("/investigations")
def investigations_list():
    investigations = get_investigations()
    assignees = sorted(set(inv["assignee"] for inv in investigations if inv["assignee"]))
    # Collect unique product areas present in active investigations (preserve order)
    seen_areas = set()
    product_areas = []
    for inv in investigations:
        area = inv.get("product_area", "other")
        if area not in seen_areas:
            seen_areas.add(area)
            product_areas.append(area)
    # Sort areas by their position in PRODUCT_AREA_RULES (canonical order), 'other' last
    canonical_order = [key for key, _, _, _ in PRODUCT_AREA_RULES]
    product_areas.sort(key=lambda a: (a == "other", canonical_order.index(a) if a in canonical_order else 999))
    return render_template(
        "investigations.html",
        investigations=investigations,
        assignees=assignees,
        statuses=VALID_STATUSES,
        status_labels=STATUS_LABELS,
        product_areas=product_areas,
        area_labels=PRODUCT_AREA_LABELS,
        area_groups=PRODUCT_AREA_GROUPS,
        area_to_group=AREA_TO_GROUP,
    )


@app.route("/investigation/<key>")
def investigation_detail(key):
    inv_dir = INVESTIGATIONS_DIR / key
    if not inv_dir.exists() or not inv_dir.is_dir():
        abort(404)

    # Read all markdown files
    md_files = {}
    for f in sorted(inv_dir.glob("*.md")):
        data = read_md_file(f)
        if data:
            md_files[f.name] = data

    # Prefer notes.md as primary, response.md as secondary
    primary = md_files.get("notes.md")
    response = md_files.get("response.md")
    other_files = {k: v for k, v in md_files.items() if k not in ("notes.md", "response.md")}

    # Check for assets
    assets_dir = inv_dir / "assets"
    assets = []
    if assets_dir.exists():
        for asset in assets_dir.rglob("*"):
            if asset.is_file() and not asset.name.startswith("."):
                assets.append({
                    "name": asset.name,
                    "path": str(asset.relative_to(ROOT)),
                    "size": asset.stat().st_size,
                    "is_image": asset.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif", ".webp"),
                })

    # Get prev/next investigation keys for navigation
    all_investigations = get_investigations()
    all_keys = [inv["key"] for inv in all_investigations]
    current_idx = all_keys.index(key) if key in all_keys else -1
    prev_key = all_keys[current_idx - 1] if current_idx > 0 else None
    next_key = all_keys[current_idx + 1] if current_idx >= 0 and current_idx < len(all_keys) - 1 else None

    # Read metadata
    meta = _read_meta(inv_dir)

    # Extract data sources from all markdown content
    all_raw = ""
    if primary:
        all_raw += primary["raw"] + "\n"
    if response:
        all_raw += response["raw"] + "\n"
    for _name, fdata in other_files.items():
        all_raw += fdata["raw"] + "\n"
    sources = extract_sources(all_raw)

    return render_template(
        "investigation_detail.html",
        key=key,
        primary=primary,
        response=response,
        other_files=other_files,
        assets=assets,
        prev_key=prev_key,
        next_key=next_key,
        meta=meta,
        valid_statuses=VALID_STATUSES,
        status_labels=STATUS_LABELS,
        sources=sources,
        sources_count=sum(len(s["refs"]) for s in sources),
    )


@app.route("/archive")
def archive():
    months = get_archive_months()
    # Collect all unique product areas across all months
    all_areas = set()
    for m in months:
        for t in m["tickets"]:
            all_areas.add(t["product_area"])
    # Build ordered list matching PRODUCT_AREA_RULES order
    area_order = [key for key, _, _, _ in PRODUCT_AREA_RULES if key in all_areas]
    return render_template(
        "archive.html",
        months=months,
        area_order=area_order,
        area_labels=PRODUCT_AREA_LABELS,
        area_groups=PRODUCT_AREA_GROUPS,
        area_to_group=AREA_TO_GROUP,
    )


@app.route("/archive/<month>/<ticket_key>")
def archive_ticket(month, ticket_key):
    ticket_path = ARCHIVE_DIR / month / f"{ticket_key}.md"
    data = read_md_file(ticket_path)
    if not data:
        abort(404)
    # Detect product area for the badge
    try:
        content_preview = ticket_path.read_text(encoding="utf-8", errors="ignore")[:2000]
    except Exception:
        content_preview = ""
    area = detect_product_area(content_preview)
    return render_template(
        "archive_ticket.html",
        ticket=data,
        key=ticket_key,
        month=month,
        product_area=area,
        area_label=PRODUCT_AREA_LABELS.get(area, area),
    )


@app.route("/docs")
def docs():
    tree = get_docs_tree()
    return render_template("docs.html", tree=tree)


@app.route("/docs/<path:doc_path>")
def doc_detail(doc_path):
    full_path = DOCS_DIR / doc_path
    if not full_path.suffix:
        full_path = full_path.with_suffix(".md")
    data = read_md_file(full_path)
    if not data:
        abort(404)
    return render_template("doc_detail.html", doc=data, doc_path=doc_path)


@app.route("/search")
def search():
    query = request.args.get("q", "").strip()
    results = []
    if query:
        results = search_files(query)
    return render_template("search.html", query=query, results=results)


@app.route("/api/search")
def api_search():
    """JSON search endpoint for AJAX."""
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify([])
    results = search_files(query, max_results=20)
    # Serialize datetimes
    for r in results:
        r["modified"] = r["modified"].isoformat()
    return jsonify(results)


# ── Investigation Meta API ────────────────────────────────────────────────────

@app.route("/api/investigation/<key>/meta", methods=["GET", "PATCH"])
def investigation_meta(key):
    """Get or update investigation metadata (status, assignee)."""
    inv_dir = INVESTIGATIONS_DIR / key
    if not inv_dir.exists() or not inv_dir.is_dir():
        return jsonify({"error": "not found"}), 404

    if request.method == "GET":
        meta = _read_meta(inv_dir)
        return jsonify(meta)

    # PATCH: update fields
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    meta = _read_meta(inv_dir)

    if "status" in data:
        if data["status"] in VALID_STATUSES:
            meta["status"] = data["status"]
        else:
            return jsonify({"error": f"Invalid status. Must be one of: {VALID_STATUSES}"}), 400

    if "assignee" in data:
        meta["assignee"] = str(data["assignee"]).strip()

    _write_meta(inv_dir, meta)
    return jsonify(meta)


@app.route("/api/investigation/<key>/watch")
def investigation_watch(key):
    """SSE endpoint: streams an event whenever files in this investigation change."""
    inv_dir = INVESTIGATIONS_DIR / key
    if not inv_dir.exists() or not inv_dir.is_dir():
        return jsonify({"error": "not found"}), 404

    def _stream():
        # Record the time we started watching
        last_seen = time.time()
        while True:
            time.sleep(1)
            with _investigation_changes_lock:
                changed_at = _investigation_changes.get(key, 0)
            if changed_at > last_seen:
                last_seen = changed_at
                # Small debounce: wait a moment for writes to finish
                time.sleep(0.5)
                yield f"data: {json.dumps({'type': 'changed', 'ts': changed_at})}\n\n"

    return Response(
        stream_with_context(_stream()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.route("/api/investigations/watch")
def investigations_list_watch():
    """SSE endpoint: streams an event when investigation folders are added or removed."""
    def _stream():
        last_seen = time.time()
        while True:
            time.sleep(1.5)
            with _investigation_changes_lock:
                changed_at = _investigation_changes.get("_list", 0)
            if changed_at > last_seen:
                last_seen = changed_at
                time.sleep(0.5)
                yield f"data: {json.dumps({'type': 'changed', 'ts': changed_at})}\n\n"

    return Response(
        stream_with_context(_stream()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.route("/api/investigation/<key>/content")
def investigation_content(key):
    """Return rendered HTML content for an investigation (for live-reload swaps)."""
    inv_dir = INVESTIGATIONS_DIR / key
    if not inv_dir.exists() or not inv_dir.is_dir():
        return jsonify({"error": "not found"}), 404

    md_files = {}
    for f in sorted(inv_dir.glob("*.md")):
        data = read_md_file(f)
        if data:
            md_files[f.name] = data

    primary = md_files.get("notes.md")
    response = md_files.get("response.md")
    other_files = {k: v for k, v in md_files.items() if k not in ("notes.md", "response.md")}

    result = {}
    if primary:
        result["notes"] = {
            "html": primary["html"],
            "path": primary["path"],
            "modified": primary["modified"].strftime("%b %d, %Y"),
            "modified_full": primary["modified"].strftime("%b %d, %Y at %I:%M %p"),
            "title": primary["title"],
            "raw": primary["raw"],
        }
    if response:
        result["response"] = {
            "html": response["html"],
            "path": response["path"],
            "raw": response["raw"],
        }
    result["other_files"] = {}
    for name, data in other_files.items():
        result["other_files"][name] = {
            "html": data["html"],
            "path": data["path"],
            "modified": data["modified"].strftime("%b %d, %Y"),
        }

    # Extract data sources for the sources panel
    all_raw = ""
    if primary:
        all_raw += primary["raw"] + "\n"
    if response:
        all_raw += response["raw"] + "\n"
    for _name, fdata in other_files.items():
        all_raw += fdata["raw"] + "\n"
    result["sources"] = extract_sources(all_raw)

    return jsonify(result)


# ── Sync / Auto-Archive API ──────────────────────────────────────────────────

# Import jira_client from scripts/
sys.path.insert(0, str(ROOT / "scripts"))

DONE_STATUSES = {"done", "done (zd automation)", "closed", "resolved", "won't do", "cancelled"}

import shutil


def _jira_fetch_full(keys: list) -> dict:
    """Fetch full issue details for a list of keys. Returns {key: issue_dict}."""
    try:
        import jira_client as jc
    except Exception:
        return {}
    if not keys:
        return {}
    result = {}
    for key in keys:
        try:
            result[key] = jc.get_issue(key)
        except Exception:
            pass
    return result


def _extract_last_activity(issue: dict, max_comments: int = 2) -> dict:
    """Extract status, updated date, assignee, and last N comments from a full issue."""
    fields = issue.get("fields", {})
    try:
        import jira_client as jc
    except Exception:
        jc = None

    status = fields.get("status", {}).get("name", "Unknown")
    updated = fields.get("updated", "")[:16].replace("T", " ")
    summary = fields.get("summary", "")

    # Assignee
    assignee_list = fields.get("customfield_11300", []) or []
    assignees = [a.get("displayName", "") for a in assignee_list if a] if assignee_list else []

    # Last comments
    comments_raw = fields.get("comment", {}).get("comments", [])
    recent_comments = []
    for c in comments_raw[-max_comments:]:
        author = c.get("author", {}).get("displayName", "Unknown")
        date = c.get("created", "")[:10]
        body = ""
        if jc:
            body = jc.extract_text(c.get("body", {}))
        # Truncate long comments
        if len(body) > 300:
            body = body[:300] + "..."
        recent_comments.append({"author": author, "date": date, "body": body})

    return {
        "status": status,
        "summary": summary,
        "updated": updated,
        "assignees": assignees,
        "last_comments": recent_comments,
    }


def _generate_summary_sync(content: str, key: str) -> str:
    """Generate a short AI summary of an investigation/ticket synchronously.

    Tries whichever LLM provider is available. Returns the summary text,
    or an empty string if no provider is available or generation fails.
    """
    prompt = (
        "You are summarising a completed security escalation ticket for archival. "
        "Write a concise TL;DR summary in 3-5 sentences. Cover: what the issue was, "
        "what the root cause turned out to be, and how it was resolved (or if it was "
        "sent back / closed without fix). Be direct and factual. Do not use headers "
        "or bullet points, just a short paragraph."
    )

    # Truncate content to avoid blowing up context windows
    max_chars = 8000
    if len(content) > max_chars:
        content = content[:max_chars] + "\n\n[...truncated for summary generation]"

    messages = [{"role": "user", "content": f"Summarise this ticket ({key}):\n\n{content}"}]

    # Try Ollama first (local, fast, no API key needed)
    try:
        payload = json.dumps({
            "model": get_chat_provider().get("model", ""),
            "messages": [{"role": "system", "content": prompt}] + messages,
            "stream": False,
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{OLLAMA_BASE_URL}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            summary = data.get("message", {}).get("content", "").strip()
            if summary:
                return summary
    except Exception:
        pass

    # Try Gemini if available
    if GEMINI_API_KEY:
        try:
            import google.generativeai as genai
            genai.configure(api_key=GEMINI_API_KEY)
            model = genai.GenerativeModel(GEMINI_MODEL, system_instruction=prompt)
            resp = model.generate_content(messages[0]["content"])
            if resp and resp.text:
                return resp.text.strip()
        except Exception:
            pass

    return ""


def _archive_from_issue(issue: dict, local_notes: str = "") -> str:
    """Write a full JIRA issue to archive/MM-YYYY/. Returns archive path.

    If local_notes is provided, it will be used alongside the JIRA content
    to generate an AI summary prepended to the archived markdown.
    """
    try:
        import jira_client as jc
    except Exception as e:
        raise RuntimeError(f"Cannot import jira_client: {e}")

    key = issue.get("key", "UNKNOWN")
    fields = issue.get("fields", {})

    created = fields.get("created", "")
    if created and len(created) >= 10:
        year = created[0:4]
        month = created[5:7]
        folder_name = f"{month}-{year}"
    else:
        folder_name = datetime.now().strftime("%m-%Y")

    month_folder = ARCHIVE_DIR / folder_name
    month_folder.mkdir(parents=True, exist_ok=True)

    md = jc.format_issue_markdown(issue)

    # Generate AI summary from JIRA content + local investigation notes
    summary_input = md
    if local_notes:
        summary_input += "\n\n---\n## Local Investigation Notes\n" + local_notes
    ai_summary = _generate_summary_sync(summary_input, key)

    if ai_summary:
        # Insert summary block right after the first heading line
        lines = md.split("\n", 1)
        heading = lines[0] if lines else f"# {key}"
        rest = lines[1] if len(lines) > 1 else ""
        md = f"{heading}\n\n> **AI Summary:** {ai_summary}\n{rest}"

    output_path = month_folder / f"{key}.md"
    with open(output_path, "w") as f:
        f.write(md)

    return str(output_path.relative_to(ROOT))


@app.route("/api/sync", methods=["POST"])
def sync_investigations():
    """Check JIRA for all active investigations.

    For tickets that are Done/Closed in JIRA:
    - Archive the JIRA ticket markdown to archive/
    - Remove the investigation folder

    For all tickets: return full context including last comments.
    """
    investigations = get_investigations()
    scrs_keys = [inv["key"] for inv in investigations if inv["key"].startswith("SCRS-")]
    zd_keys = [inv["key"] for inv in investigations if not inv["key"].startswith("SCRS-")]

    if not scrs_keys:
        return jsonify({"checked": 0, "archived": [], "still_active": [], "errors": [], "skipped": zd_keys})

    # Fetch full details for every active investigation
    full_issues = _jira_fetch_full(scrs_keys)

    archived = []
    still_active = []
    errors = []

    for key in scrs_keys:
        issue = full_issues.get(key)
        if not issue:
            errors.append({"key": key, "error": "Could not fetch from JIRA"})
            continue

        activity = _extract_last_activity(issue)
        jira_status = activity["status"]

        if jira_status.lower().strip() in DONE_STATUSES:
            try:
                # Read local investigation notes before deleting the folder
                inv_dir = INVESTIGATIONS_DIR / key
                local_notes = ""
                if inv_dir.exists():
                    for md_name in ("notes.md", "response.md"):
                        md_path = inv_dir / md_name
                        if md_path.exists():
                            try:
                                local_notes += f"\n\n### {md_name}\n" + md_path.read_text()
                            except Exception:
                                pass
                archive_path = _archive_from_issue(issue, local_notes=local_notes)
                if inv_dir.exists():
                    shutil.rmtree(inv_dir)
                archived.append({
                    "key": key,
                    "jira_status": jira_status,
                    "archive_path": archive_path,
                    **activity,
                })
            except Exception as e:
                errors.append({"key": key, "error": str(e)})
        else:
            still_active.append({"key": key, "jira_status": jira_status, **activity})

    return jsonify({
        "checked": len(scrs_keys),
        "archived": archived,
        "still_active": still_active,
        "errors": errors,
        "skipped": zd_keys,
    })


@app.route("/api/sync/preview", methods=["GET"])
def sync_preview():
    """Preview: check JIRA statuses and pull last activity for all investigations."""
    investigations = get_investigations()
    scrs_keys = [inv["key"] for inv in investigations if inv["key"].startswith("SCRS-")]
    zd_keys = [inv["key"] for inv in investigations if not inv["key"].startswith("SCRS-")]

    if not scrs_keys:
        return jsonify({"checked": 0, "would_archive": [], "still_active": [], "skipped": zd_keys})

    full_issues = _jira_fetch_full(scrs_keys)

    would_archive = []
    still_active = []

    for key in scrs_keys:
        issue = full_issues.get(key)
        if not issue:
            still_active.append({"key": key, "jira_status": "(not found)", "summary": "", "updated": "", "assignees": [], "last_comments": []})
            continue

        activity = _extract_last_activity(issue)
        jira_status = activity["status"]

        if jira_status.lower().strip() in DONE_STATUSES:
            would_archive.append({"key": key, "jira_status": jira_status, **activity})
        else:
            still_active.append({"key": key, "jira_status": jira_status, **activity})

    return jsonify({
        "checked": len(scrs_keys),
        "would_archive": would_archive,
        "still_active": still_active,
        "skipped": zd_keys,
    })


# ── Chat API ─────────────────────────────────────────────────────────────────

@app.route("/api/chat/status")
def chat_status():
    """Check if chat is available and which provider is active."""
    provider = get_chat_provider()
    return jsonify(provider)


@app.route("/api/chat/context/<key>")
def chat_context(key):
    """Get the context for a specific investigation to inject into chat."""
    inv_dir = INVESTIGATIONS_DIR / key
    if not inv_dir.exists():
        return jsonify({"error": "not found"}), 404

    context_parts = []
    for md_file in sorted(inv_dir.glob("*.md")):
        try:
            content = md_file.read_text(encoding="utf-8")
            context_parts.append(f"--- {md_file.name} ---\n{content}")
        except Exception:
            continue

    return jsonify({
        "key": key,
        "context": "\n\n".join(context_parts),
    })


def _build_system_prompt(investigation_context: str = "") -> str:
    """Build the full system prompt with optional investigation context."""
    system = SYSTEM_PROMPT
    if investigation_context:
        system += (
            "\n\n--- CURRENT INVESTIGATION CONTEXT ---\n"
            "The user is currently viewing the following investigation. "
            "Use this context to inform your answers.\n\n"
            + investigation_context
        )
    return system


def _stream_anthropic(messages, system, model):
    """Stream from Anthropic Claude API."""
    import anthropic

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        with client.messages.stream(
            model=model,
            max_tokens=4096,
            system=system,
            messages=messages,
        ) as stream:
            for text in stream.text_stream:
                yield f"data: {json.dumps({'type': 'text', 'text': text})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
    except anthropic.AuthenticationError:
        yield f"data: {json.dumps({'type': 'error', 'text': 'Invalid API key. Check ANTHROPIC_API_KEY in your .env file.'})}\n\n"
    except anthropic.RateLimitError:
        yield f"data: {json.dumps({'type': 'error', 'text': 'Rate limited by Anthropic. Wait a moment and try again.'})}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'text': str(e)})}\n\n"


def _stream_gemini(messages, system, model):
    """Stream from Gemini with function-calling (tool use) support."""
    import google.generativeai as genai
    from tools import ALL_TOOL_FUNCTIONS, TOOL_FUNCTIONS, TOOL_UI_LABELS

    try:
        genai.configure(api_key=GEMINI_API_KEY)
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'text': f'Gemini config error: {e}'})}\n\n"
        return

    try:
        gmodel = genai.GenerativeModel(
            model_name=model,
            system_instruction=system,
            tools=ALL_TOOL_FUNCTIONS,
        )
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'text': f'Gemini model init error: {e}'})}\n\n"
        return

    # Convert message history to Gemini format (all but last message as history)
    gemini_history = []
    for msg in messages[:-1]:
        role = "user" if msg["role"] == "user" else "model"
        gemini_history.append({"role": role, "parts": [msg["content"]]})

    try:
        chat_session = gmodel.start_chat(history=gemini_history)
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'text': f'Chat session error: {e}'})}\n\n"
        return

    last_message = messages[-1]["content"]
    max_tool_turns = 8

    try:
        for _turn in range(max_tool_turns):
            response = chat_session.send_message(last_message)

            # Collect function calls from this response
            fn_calls = []
            for part in response.parts:
                try:
                    if part.function_call and part.function_call.name:
                        fn_calls.append(part.function_call)
                except (AttributeError, ValueError):
                    continue

            if not fn_calls:
                # Final text response, deliver it
                text = response.text or ""
                if text:
                    # Send in chunks for a responsive feel
                    chunk_size = 80
                    for i in range(0, len(text), chunk_size):
                        yield f"data: {json.dumps({'type': 'text', 'text': text[i:i+chunk_size]})}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                return

            # Execute each function call and collect responses
            fn_response_parts = []
            for fc in fn_calls:
                name = fc.name
                args = dict(fc.args) if fc.args else {}

                # Get a display-friendly summary of args
                display_arg = ""
                if args:
                    first_val = next(iter(args.values()), "")
                    display_arg = str(first_val)[:60]

                label = TOOL_UI_LABELS.get(name, name)
                yield f"data: {json.dumps({'type': 'tool_start', 'tool': name, 'label': label, 'detail': display_arg})}\n\n"

                # Execute the tool
                try:
                    if name in TOOL_FUNCTIONS:
                        result = TOOL_FUNCTIONS[name](**args)
                    else:
                        result = f"Unknown tool: {name}"
                except Exception as e:
                    result = f"Tool error: {e}"

                yield f"data: {json.dumps({'type': 'tool_end', 'tool': name})}\n\n"

                fn_response_parts.append(
                    genai.protos.Part(
                        function_response=genai.protos.FunctionResponse(
                            name=name,
                            response={"result": result},
                        )
                    )
                )

            # Send all function results back to Gemini for next turn
            last_message = fn_response_parts

        # If we exhausted max turns
        yield f"data: {json.dumps({'type': 'error', 'text': 'Reached maximum tool call rounds. Try a more specific question.'})}\n\n"

    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'text': f'Gemini error: {e}'})}\n\n"


def _stream_ollama(messages, system, model):
    """Stream from local Ollama API."""
    # Ollama uses the OpenAI-style messages format with a system role
    ollama_messages = [{"role": "system", "content": system}] + messages

    payload = json.dumps({
        "model": model,
        "messages": ollama_messages,
        "stream": True,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{OLLAMA_BASE_URL}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            for line in resp:
                line = line.decode("utf-8").strip()
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                    if chunk.get("done"):
                        yield f"data: {json.dumps({'type': 'done'})}\n\n"
                        break
                    text = chunk.get("message", {}).get("content", "")
                    if text:
                        yield f"data: {json.dumps({'type': 'text', 'text': text})}\n\n"
                except json.JSONDecodeError:
                    continue
    except urllib.error.URLError as e:
        yield f"data: {json.dumps({'type': 'error', 'text': f'Ollama connection failed: {e.reason}. Is Ollama running?'})}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'text': str(e)})}\n\n"


@app.route("/api/chat", methods=["POST"])
def chat():
    """Stream a chat response, auto-selecting provider."""
    provider = get_chat_provider()
    if not provider["available"]:
        return jsonify({"error": "No chat provider available. Add GEMINI_API_KEY to .env (free), or set up Ollama/Anthropic."}), 503

    data = request.get_json()
    if not data or "messages" not in data:
        return jsonify({"error": "messages required"}), 400

    messages = data["messages"]
    investigation_context = data.get("context", "")
    system = _build_system_prompt(investigation_context)

    # Allow frontend to override model
    model = data.get("model") or provider["model"]

    if provider["provider"] == "anthropic":
        gen = _stream_anthropic(messages, system, model)
    elif provider["provider"] == "gemini":
        gen = _stream_gemini(messages, system, model)
    elif provider["provider"] == "ollama":
        gen = _stream_ollama(messages, system, model)
    else:
        return jsonify({"error": "Unknown provider"}), 500

    return Response(
        stream_with_context(gen),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── Error Handlers ───────────────────────────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404


# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="TEE Hub local web server")
    parser.add_argument("--port", type=int, default=5001, help="Port to run on (default: 5001)")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    args = parser.parse_args()

    provider = get_chat_provider()

    # Start file watcher for live-reload
    _start_file_watcher()

    print(f"\n  TEE Hub running at http://localhost:{args.port}\n")
    print(f"  Workspace: {ROOT}")
    print(f"  Investigations: {len(get_investigations())}")
    print(f"  Archive months: {len(get_archive_months())}")
    if provider["available"]:
        print(f"  Chat: {provider['label']}")
    else:
        print(f"  Chat: not available (add GEMINI_API_KEY to .env, or set up Ollama/Anthropic)")
    print()

    app.run(host="127.0.0.1", port=args.port, debug=args.debug)

