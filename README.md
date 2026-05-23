# WhatsApp CRM Review Intelligence

Scrapes Google Reviews for WhatsApp CRM companies (Gallabox, AiSensy, Wati, Interakt, Zoko), analyzes them with AI, and generates actionable insights.

## Architecture

```
FastAPI ──→ Celery ──→ Playwright (scrape)
                  ──→ Groq API (analyze)
                  ──→ sentence-transformers (embeddings)
                  ──→ Groq API (insights)
         ↑
    Redis (broker)
         ↓
    PostgreSQL (storage)
```

## Prerequisites

- Python 3.14+
- [uv](https://docs.astral.sh/uv/) (package manager)
- PostgreSQL 16/17
- Redis
- Groq API key (https://console.groq.com)

## Setup

### 1. Clone & init

```bash
git clone <repo> && cd <repo>
uv venv
```

### 2. Install dependencies

```bash
uv sync
playwright install chromium
```

### 3. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

| Variable | Description | Example |
|---|---|---|
| `DATABASE_URL` | Async PostgreSQL connection string | `postgresql+asyncpg://postgres:postgres@localhost:5432/review_intel` |
| `REDIS_URL` | Redis connection string | `redis://localhost:6379/0` |
| `GROQ_API_KEY` | Your Groq API key | `gsk-...` |
| `GROQ_MODEL` | Model to use (optional) | `llama-3.3-70b-versatile` |

### 4. Create database

```bash
psql -U postgres -c "CREATE DATABASE review_intel;"
```

Tables are auto-created on first app startup.

## Running

Run these three commands in **separate terminals**:

### Terminal 1 — Celery worker

```bash
uv run celery -A app.workers.celery_app worker -Q scrape_queue,analysis_queue -E --loglevel=info
```

### Terminal 2 — FastAPI server

```bash
uv run uvicorn app.main:app --reload --port 8000
```

### Terminal 3 — (optional) Flower monitoring

```bash
uv run celery -A app.workers.celery_app flower --port=5555
```

## API Usage

### Add a company

```bash
curl -X POST http://localhost:8000/api/v1/companies \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Gallabox",
    "website": "https://gallabox.com",
    "google_maps_url": "https://maps.google.com/maps?cid=..."
  }'
```

### List companies

```bash
curl http://localhost:8000/api/v1/companies
```

### Scrape reviews (async — returns immediately)

```bash
curl -X POST http://localhost:8000/api/v1/companies/1/scrape
```

### Check reviews

```bash
curl http://localhost:8000/api/v1/companies/1/reviews
```

### Run AI analysis (async)

```bash
curl -X POST http://localhost:8000/api/v1/companies/1/analyze
```

### Get insights

```bash
curl http://localhost:8000/api/v1/companies/1/insights
```

## Pipeline Flow

```
POST /companies/1/scrape
  ↓ (Celery: scrape_queue)
Playwright scrapes Google Maps reviews
  ↓
Store raw reviews in PostgreSQL
  ↓ (auto-enqueues)
POST /companies/1/analyze
  ↓ (Celery: analysis_queue)
Groq: sentiment + category per review
  ↓
sentence-transformers: embeddings per review
  ↓
Groq: chunk-level summaries → combined insight
  ↓
Store analysis + insights in PostgreSQL
```

## Target Companies

| Company | Product |
|---|---|
| Gallabox | WhatsApp business platform |
| AiSensy | WhatsApp marketing |
| Wati | WhatsApp CRM |
| Interakt | WhatsApp commerce |
| Zoko | WhatsApp sales platform |

## Project Structure

```
app/
├── main.py                    # FastAPI entrypoint
├── api/routes.py              # REST endpoints
├── core/config.py             # pydantic-settings
├── db/
│   ├── base.py                # DeclarativeBase
│   └── session.py             # async engine + session
├── models/                    # SQLAlchemy ORM models
├── schemas/                   # Pydantic request/response
├── services/
│   ├── scraping/              # Playwright Google Maps scraper
│   ├── ai/                    # Groq analysis
│   ├── embeddings/            # sentence-transformers
│   └── insights/              # Aggregated insights
├── workers/
│   ├── celery_app.py          # Celery config
│   └── tasks.py               # scrape + analyze tasks
└── utils/
    ├── log_config.py          # Structured logging
    └── dedup.py               # Duplicate review detection
```

## Troubleshooting

**Database connection refused** — ensure PostgreSQL is running:
```bash
pg_isready -h localhost
```

**Redis connection refused** — ensure Redis is running:
```bash
redis-cli ping
# → PONG
```

**Playwright navigation fails** — Google Maps may require location cookies. Run with `headless=False` temporarily for debugging. Update `playwright_helpers.py`:
```python
headless=False,  # default: True
```

**Groq rate limits** — check your Groq API key has available rate limits. Reduce `max_reviews_per_company` in `config.py` to test with fewer reviews.
