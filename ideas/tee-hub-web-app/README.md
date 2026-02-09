# TEE Hub Web App

**Status:** 💭 Concept  
**Created:** Jan 2026  
**Priority:** Low (future exploration)  
**Deployment:** 🏠 Local-first (Docker Compose)

## Overview

A standalone web application that provides a UI for TEE investigations, replacing the Cursor-based workflow with a dedicated tool. **Runs entirely on the user's machine** — no hosting costs, no shared secrets.

## Why Local-First?

- ✅ **$0 infrastructure cost** — runs on your laptop
- ✅ **No shared secrets** — each user uses their own API keys
- ✅ **Works offline** — great for travel, unreliable wifi
- ✅ **Privacy** — investigation data stays local
- ✅ **Simple setup** — just `docker compose up`
- ✅ **No maintenance burden** — users update themselves

## Proposed Tech Stack

| Layer | Tech | Why |
|-------|------|-----|
| Frontend | Next.js + React | Fast, SSR, great DX |
| UI | shadcn/ui + Tailwind | Modern, customizable |
| Backend | Next.js API Routes | Keep it simple |
| AI | Claude API (user's key) | Best reasoning |
| Database | PostgreSQL (Docker) | Local, persistent |
| Vector Search | pgvector | Semantic search, no extra service |
| Auth | None (single user) | Not needed locally |
| Runtime | Docker Compose | One command setup |

## Core Features

### 1. Investigation Dashboard
- Input SCRS ticket number
- Auto-fetch from JIRA
- Display escalation quality assessment
- Show similar historical cases
- AI-generated analysis + next steps

### 2. Escalation Quality Checker
- Automated assessment of what TSE provided
- Checklist of missing information
- Generate response template for TSE

### 3. Semantic Search
- Vector embeddings of all archived tickets
- "Find similar cases" based on meaning, not keywords
- Surface relevant historical resolutions

### 4. TSE Response Generator
- AI-drafted responses based on analysis
- Customizable templates
- One-click copy

## Architecture

```
Browser → Next.js App → Claude API
                ↓
         JIRA / GitHub / Confluence APIs
                ↓
         PostgreSQL + pgvector
```

See [architecture.md](./architecture.md) for full details.

## UI Mockups

See [mockups/](./mockups/) folder.

## MVP Scope

**Must Have:**
- [ ] Input ticket → fetch from JIRA
- [ ] Escalation quality assessment
- [ ] AI-generated analysis
- [ ] Similar cases search
- [ ] Investigation notes

**Nice to Have:**
- [ ] TSE response generator
- [ ] GitHub code search
- [ ] Team dashboard / stats

## Local Setup Experience

```bash
# 1. Clone the repo
git clone git@github.com:DataDog/tee-hub.git
cd tee-hub

# 2. Copy env template, add your API keys
cp .env.example .env.local
# Edit .env.local:
#   ANTHROPIC_API_KEY=sk-...
#   JIRA_TOKEN=ATATT...
#   JIRA_EMAIL=you@datadoghq.com
#   GITHUB_TOKEN=ghp_...

# 3. Start everything
make up   # or: docker compose up -d

# 4. Open browser
open http://localhost:3000

# To stop:
make down
```

## Docker Compose Setup

```yaml
# docker-compose.yml
version: '3.8'

services:
  app:
    build: .
    ports:
      - "3000:3000"
    environment:
      DATABASE_URL: postgresql://tee:tee@db:5432/teehub
    env_file:
      - .env.local
    volumes:
      - ./data/assets:/app/assets
    depends_on:
      - db

  db:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: tee
      POSTGRES_PASSWORD: tee
      POSTGRES_DB: teehub
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    ports:
      - "5432:5432"
```

## Local Data Storage

```
~/.tee-hub/                    # Or ./data/ in repo
├── postgres/                  # Database files
├── archive/                   # Exported JIRA tickets
└── assets/                    # Flares, logs, screenshots
```

## Cost Analysis

### Infrastructure: $0

| Item | Cost |
|------|------|
| Hosting | $0 (your laptop) |
| Database | $0 (Docker Postgres) |
| Storage | $0 (local disk) |
| Auth | $0 (none needed) |
| **Total** | **$0/month** |

### User API Costs (per user)

| Service | Est. Cost |
|---------|-----------|
| Claude API | ~$5-15/mo (depends on usage) |
| OpenAI Embeddings | ~$1/mo |
| JIRA/GitHub | $0 (existing tokens) |
| **Total** | **~$6-16/mo per user** |

## Open Questions

1. **Shared knowledge** — How to share learnings across TEEs? (Maybe sync archive folder?)
2. **Updates** — How do users get new versions? (git pull + rebuild)
3. **SQLite option** — Could skip Docker entirely with SQLite + sqlite-vss

## Next Steps

When ready to explore:
1. Scaffold Next.js project with Docker Compose
2. Build JIRA integration first
3. Add local Postgres + pgvector
4. Add AI layer (Claude)
5. Test with real investigations
6. Share repo with team

