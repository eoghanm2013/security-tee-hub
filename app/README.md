# TEE Hub Web App

> Local web UI for browsing investigations, archived tickets, and docs. Optional AI chat built in.

---

**Quick Start**

```bash
./app/run.sh
```

Opens at http://localhost:5001. First run creates a virtual environment and installs dependencies automatically.

Custom port: `./app/run.sh --port 8080`
Debug mode (auto-reload): `./app/run.sh --debug`

---

**What It Does**

- **Dashboard** - Overview of active investigations, archive stats, and docs count
- **Investigations** - Browse all active `investigations/SCRS-XXXX` folders with rendered markdown, status tracking, product area detection, and source extraction (JIRA links, Slack refs, GitHub links, Datadog docs)
- **Archive** - Browse archived tickets by month, filterable by product area
- **Docs** - Browse the `docs/` tree with rendered markdown
- **Search** - Full-text search across investigations, archive, and docs
- **Live Reload** - Investigation pages auto-refresh when you edit files in Cursor (uses filesystem watcher + SSE)
- **AI Chat** (optional) - Context-aware chat panel on investigation pages with tool use (JIRA search, local file search)

---

**AI Chat Providers**

The chat panel works with any one of these (checked in order):

| Provider | Env Variable | Notes |
|----------|-------------|-------|
| Anthropic (Claude) | `ANTHROPIC_API_KEY` | Paid API |
| Gemini | `GEMINI_API_KEY` | Free tier available, supports tool calling |
| Ollama | `OLLAMA_BASE_URL` (default: localhost:11434) | Local, no API key needed, auto-detects models |

Add the key to your `.env` file at the project root. Chat is optional, the app works fine without it.

---

**Chat Tools**

When using Gemini (tool-calling enabled), the chat can:
- **Search workspace** - Find content across local investigations, archive, and docs
- **Read investigation** - Load full contents of a specific ticket's notes
- **Fetch JIRA ticket** - Pull live ticket data from JIRA API
- **Search JIRA** - Run JQL queries against JIRA

---

**File Structure**

```
app/
├── server.py          # Flask app (routes, helpers, chat streaming, sync API)
├── tools.py           # Chat tool functions (JIRA, local search)
├── run.sh             # Startup script (creates venv, installs deps, runs server)
├── requirements.txt   # Python dependencies
├── templates/         # Jinja2 HTML templates
│   ├── base.html
│   ├── dashboard.html
│   ├── investigations.html
│   ├── investigation_detail.html
│   ├── archive.html
│   ├── archive_ticket.html
│   ├── docs.html
│   ├── doc_detail.html
│   ├── search.html
│   └── 404.html
└── static/            # CSS, JS, images
```

---

**API Endpoints**

| Endpoint | Method | What |
|----------|--------|------|
| `/api/search?q=` | GET | Full-text search (JSON) |
| `/api/investigation/<key>/meta` | GET/PATCH | Read or update investigation status/assignee |
| `/api/investigation/<key>/watch` | GET (SSE) | Live-reload stream for file changes |
| `/api/investigation/<key>/content` | GET | Rendered HTML content for live-reload |
| `/api/investigations/watch` | GET (SSE) | Stream for new/deleted investigation folders |
| `/api/sync/preview` | GET | Preview which investigations would be archived (checks JIRA status) |
| `/api/sync` | POST | Auto-archive investigations that are Done/Closed in JIRA |
| `/api/chat/status` | GET | Check chat provider availability |
| `/api/chat` | POST | Stream chat response (SSE) |

---

**Sync / Auto-Archive**

The dashboard has a sync button that:
1. Checks JIRA status for all active SCRS investigations
2. If a ticket is Done/Closed in JIRA, archives it to `archive/MM-YYYY/`
3. Generates an AI summary (if chat provider available) prepended to the archived markdown
4. Removes the investigation folder after archiving

Use preview first (`/api/sync/preview`) to see what would be archived before committing.

---

**Dependencies**

- `flask` - Web framework
- `markdown` + `pygments` - Markdown rendering with syntax highlighting
- `watchdog` - Filesystem watcher for live-reload
- `anthropic` / `google-generativeai` - Chat providers (optional, only needed if using chat)

