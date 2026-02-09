# Architecture

**Deployment Model:** Local-first (Docker Compose on user's machine)

## System Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           USER'S LAPTOP                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │                        DOCKER COMPOSE                                  │ │
│  │                                                                        │ │
│  │  ┌─────────────────────────────────────┐    ┌───────────────────────┐ │ │
│  │  │          NEXT.JS APP                │    │  POSTGRES + PGVECTOR  │ │ │
│  │  │          localhost:3000             │◄──►│  localhost:5432       │ │ │
│  │  │                                     │    │                       │ │ │
│  │  │  ┌───────────┐  ┌───────────────┐  │    │  - Investigations     │ │ │
│  │  │  │  React UI │  │  API Routes   │  │    │  - Archived tickets   │ │ │
│  │  │  └───────────┘  └───────────────┘  │    │  - Vector embeddings  │ │ │
│  │  └─────────────────────────────────────┘    └───────────────────────┘ │ │
│  │                     │                                                  │ │
│  └─────────────────────┼──────────────────────────────────────────────────┘ │
│                        │                                                    │
│  ┌─────────────────────┼──────────────────────────────────────────────────┐ │
│  │                     ▼           LOCAL STORAGE                          │ │
│  │  ./data/                                                               │ │
│  │  ├── postgres/          # Database files (persistent)                  │ │
│  │  ├── assets/            # Flares, logs, screenshots                    │ │
│  │  └── archive/           # Exported ticket JSONs                        │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                    .env.local (USER'S API KEYS)                        │ │
│  │  ANTHROPIC_API_KEY=sk-ant-...                                          │ │
│  │  JIRA_EMAIL=you@datadoghq.com                                          │ │
│  │  JIRA_TOKEN=ATATT...                                                   │ │
│  │  GITHUB_TOKEN=ghp_...                                                  │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼ HTTPS (user's keys)
                    ┌──────────────────────────────────────┐
                    │          EXTERNAL APIS               │
                    │  ┌────────┐ ┌────────┐ ┌──────────┐  │
                    │  │ Claude │ │  JIRA  │ │  GitHub  │  │
                    │  │  API   │ │  API   │ │   API    │  │
                    │  └────────┘ └────────┘ └──────────┘  │
                    └──────────────────────────────────────┘
```

## Data Flow

### Investigation Flow

```
1. User enters SCRS-XXXX
          │
          ▼
2. API fetches ticket from JIRA
          │
          ▼
3. AI assesses escalation quality
          │
          ▼
4. Vector search finds similar cases
          │
          ▼
5. AI generates analysis + recommendations
          │
          ▼
6. Results displayed in UI
          │
          ▼
7. User can save notes, generate responses
```

### Archive Flow

```
1. Cron job or manual trigger
          │
          ▼
2. Fetch resolved tickets from JIRA (last N days)
          │
          ▼
3. Generate embeddings for each ticket
          │
          ▼
4. Store in PostgreSQL with pgvector
          │
          ▼
5. Available for semantic search
```

## Database Schema

```prisma
model User {
  id            String   @id @default(cuid())
  email         String   @unique
  name          String
  investigations Investigation[]
}

model Investigation {
  id            String   @id @default(cuid())
  ticketKey     String   @unique
  status        Status   @default(TRIAGE)
  
  // Cached JIRA data
  summary       String
  description   String
  reporter      String
  priority      String
  
  // TEE work
  notes         String?  @db.Text
  qualityScore  Int?
  rootCause     String?
  resolution    String?
  
  // Relationships
  userId        String
  user          User     @relation(fields: [userId], references: [id])
  
  createdAt     DateTime @default(now())
  updatedAt     DateTime @updatedAt
}

model ArchivedTicket {
  id            String   @id @default(cuid())
  ticketKey     String   @unique
  data          Json
  embedding     Unsupported("vector(1536)")
  archivedAt    DateTime @default(now())
}

enum Status {
  TRIAGE
  INVESTIGATING
  BLOCKED
  WAITING_TSE
  ESCALATED_ENG
  RESOLVED
}
```

## API Routes

| Route | Method | Description |
|-------|--------|-------------|
| `/api/investigate` | POST | Start new investigation |
| `/api/investigate/[key]` | GET | Get investigation details |
| `/api/investigate/[key]/notes` | PUT | Update investigation notes |
| `/api/jira/[key]` | GET | Fetch ticket from JIRA |
| `/api/search` | POST | Semantic search |
| `/api/ai/analyze` | POST | AI analysis |
| `/api/ai/response` | POST | Generate TSE response |

## Environment Variables

```bash
# .env.local (each user creates their own)

# Database (auto-configured by Docker Compose)
DATABASE_URL="postgresql://tee:tee@localhost:5432/teehub"

# JIRA (user's own token)
JIRA_URL="https://datadoghq.atlassian.net"
JIRA_EMAIL="you@datadoghq.com"
JIRA_TOKEN="ATATT..."

# Confluence (same token works)
CONFLUENCE_URL="https://datadoghq.atlassian.net/wiki"

# GitHub (user's own PAT)
GITHUB_TOKEN="ghp_..."

# AI (user's own keys)
ANTHROPIC_API_KEY="sk-ant-..."
OPENAI_API_KEY="sk-..."  # For embeddings only
```

## Security Considerations

1. **No shared secrets** — each user has their own `.env.local`
2. **No auth needed** — single user, runs locally
3. **Data stays local** — nothing leaves the user's machine except API calls
4. **Git-ignored** — `.env.local` and `./data/` never committed

## Docker Compose

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
      db:
        condition: service_healthy

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
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U tee -d teehub"]
      interval: 5s
      timeout: 5s
      retries: 5
```

## Makefile (Developer Experience)

```makefile
# Makefile

.PHONY: up down logs shell db-shell reset

up:
	docker compose up -d
	@echo "🚀 TEE Hub running at http://localhost:3000"

down:
	docker compose down

logs:
	docker compose logs -f app

shell:
	docker compose exec app sh

db-shell:
	docker compose exec db psql -U tee -d teehub

reset:
	docker compose down -v
	rm -rf ./data/postgres
	@echo "🗑️  Database reset. Run 'make up' to start fresh."
```

