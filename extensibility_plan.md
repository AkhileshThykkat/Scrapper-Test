# Extensibility Plan — Multi-Source Review Intelligence

## 1. Vision

Transform this system from a single-source Google Maps scraper into a **multi-source competitive intelligence platform** that:

- Scrapes reviews from **any review site** (G2, Capterra, Trustpilot, TrustRadius, etc.)
- Handles **authenticated/login-gated** review platforms
- Runs **periodically** (weekly/biweekly) with smart dedup
- Builds a **cumulative knowledge base** of pain points per company over time

---

## 2. Scraper Architecture — Plugin System

### 2.1 Base Scraper Interface

```python
# app/services/scraping/base.py

from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class ScrapedReview:
    """Normalized review from any source."""
    reviewer_name: str | None
    rating: int | float | None     # Normalized to 1-5 scale
    review_text: str | None
    review_date: str | None
    source: str                     # "g2", "capterra", "google_maps", etc.
    source_url: str | None          # Original review URL
    source_review_id: str | None    # Platform-specific unique ID for dedup
    raw_metadata: dict | None       # Source-specific extras (role, company size, etc.)

class BaseScraper(ABC):
    """All scrapers implement this interface."""

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Unique identifier: 'g2', 'capterra', 'trustpilot', etc."""

    @abstractmethod
    async def scrape(self, company_name: str, source_url: str, **kwargs) -> list[ScrapedReview]:
        """Scrape reviews for a company from this source."""

    @abstractmethod
    async def validate_url(self, url: str) -> bool:
        """Check if a URL belongs to this scraper's platform."""
```

### 2.2 Scraper Registry

```python
# app/services/scraping/registry.py

_scrapers: dict[str, type[BaseScraper]] = {}

def register_scraper(cls):
    """Decorator to register a scraper plugin."""
    _scrapers[cls.source_name] = cls
    return cls

def get_scraper(source: str) -> BaseScraper:
    if source not in _scrapers:
        raise ValueError(f"Unknown source: {source}. Available: {list(_scrapers.keys())}")
    return _scrapers[source]()

def list_sources() -> list[str]:
    return list(_scrapers.keys())
```

### 2.3 Platform-Specific Scrapers

Each platform gets its own file under `app/services/scraping/sources/`:

```
app/services/scraping/
├── base.py                    # BaseScraper ABC + ScrapedReview
├── registry.py                # Plugin registry
├── playwright_helpers.py      # Shared browser utilities
└── sources/
    ├── __init__.py
    ├── google_maps.py         # @register_scraper — Google Maps
    ├── g2.py                  # @register_scraper — G2.com
    ├── capterra.py            # @register_scraper — Capterra
    ├── trustpilot.py          # @register_scraper — Trustpilot
    ├── trustradius.py         # @register_scraper — TrustRadius
    └── custom_site.py         # @register_scraper — Generic/custom
```

### 2.4 Company Model Extension

The `Company` model should support **multiple review sources**:

```python
# New model: CompanySource
class CompanySource(Base):
    __tablename__ = "company_sources"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    source: Mapped[str] = mapped_column(String(64))          # "g2", "capterra", etc.
    source_url: Mapped[str] = mapped_column(String(1024))     # URL to scrape
    requires_auth: Mapped[bool] = mapped_column(default=False)
    auth_config_id: Mapped[int | None] = mapped_column(ForeignKey("auth_configs.id"))
    last_scraped_at: Mapped[datetime | None]
    is_active: Mapped[bool] = mapped_column(default=True)
```

### 2.5 API Changes

```
POST /api/v1/companies/{id}/sources
  body: { "source": "g2", "source_url": "https://www.g2.com/products/gallabox/reviews" }

POST /api/v1/companies/{id}/scrape
  body: { "sources": ["g2", "capterra"] }   # or omit to scrape all active sources

GET  /api/v1/companies/{id}/reviews?source=g2&sentiment=negative
```

---

## 3. Authenticated / Login-Gated Scraping

Some platforms (G2 detailed views, app stores with geo-restrictions, internal tools) require login.

### 3.1 Auth Strategy Options

| Strategy | Use Case | Implementation |
|---|---|---|
| **Cookie Injection** | Sites where you can extract session cookies from a real login | Store encrypted cookies in DB; inject into Playwright context before navigation |
| **Credential-Based Login** | Sites with standard login forms | Automate form fill + submit via Playwright; handle 2FA via TOTP |
| **API Token** | Platforms with review APIs (G2, Trustpilot) | Use official/unofficial APIs instead of scraping |
| **Browser Profile Persistence** | Sites with complex auth flows | Persist and reuse Playwright `storageState` (cookies + localStorage) |

### 3.2 Auth Config Model

```python
class AuthConfig(Base):
    __tablename__ = "auth_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))                # "G2 Production Account"
    auth_type: Mapped[str] = mapped_column(String(32))            # "cookie", "credentials", "api_token", "storage_state"

    # Encrypted storage — never store plaintext credentials
    encrypted_credentials: Mapped[str | None] = mapped_column(Text)  # Fernet-encrypted JSON
    storage_state_path: Mapped[str | None] = mapped_column(String(512))  # Path to Playwright storageState file

    last_validated_at: Mapped[datetime | None]
    is_valid: Mapped[bool] = mapped_column(default=True)
```

### 3.3 Authenticated Playwright Context

```python
# app/services/scraping/auth_helpers.py

async def get_authenticated_context(auth_config: AuthConfig) -> BrowserContext:
    """Create a Playwright context pre-loaded with auth state."""

    match auth_config.auth_type:
        case "storage_state":
            # Reuse saved cookies + localStorage from a previous manual login
            context = await browser.new_context(
                storage_state=auth_config.storage_state_path
            )

        case "cookie":
            context = await browser.new_context()
            cookies = decrypt_and_parse(auth_config.encrypted_credentials)
            await context.add_cookies(cookies)

        case "credentials":
            context = await browser.new_context()
            creds = decrypt_and_parse(auth_config.encrypted_credentials)
            page = await context.new_page()
            await _perform_login(page, creds)  # Platform-specific login automation
            await page.close()

        case "api_token":
            # Not browser-based; used by API-based scrapers
            pass

    return context
```

### 3.4 Storage State Capture Workflow

For complex auth flows (SSO, OAuth, CAPTCHA), provide a **manual login capture** tool:

```bash
# CLI command: opens a visible browser, user logs in manually, state is saved
uv run python -m app.tools.capture_auth --source g2 --name "G2 Account"

# What it does:
# 1. Opens Playwright in headful mode (headless=False)
# 2. Navigates to the login page
# 3. Waits for the user to login manually
# 4. Saves context.storage_state() to encrypted file
# 5. Stores reference in auth_configs table
```

### 3.5 Auth Validation & Rotation

```python
# Before each scrape, validate auth is still active:
async def validate_auth(auth_config: AuthConfig, source_scraper: BaseScraper) -> bool:
    # Load context with stored auth
    # Navigate to a known authenticated page
    # Check if login wall appears
    # If invalid: mark auth_config.is_valid = False, alert admin
    pass
```

---

## 4. Periodic Scraping & Smart Dedup

### 4.1 Scheduling

Use **Celery Beat** for periodic scheduling:

```python
# celery_app.py
celery_app.conf.beat_schedule = {
    "scrape-all-companies": {
        "task": "app.workers.tasks.periodic_scrape_all",
        "schedule": crontab(day_of_week=1, hour=2, minute=0),  # Every Monday 2 AM
    },
}
```

### 4.2 Review Fingerprinting (Enhanced Dedup)

Current dedup uses `reviewer_name + text[:100] + date` — fragile for cross-source dedup.

**Improved approach**: Generate a content hash fingerprint for each review:

```python
import hashlib

def review_fingerprint(source: str, reviewer: str, text: str, date: str) -> str:
    """Deterministic fingerprint for dedup across runs and sources."""
    normalized = f"{source}|{(reviewer or '').strip().lower()}|{(text or '').strip().lower()[:200]}|{date or ''}"
    return hashlib.sha256(normalized.encode()).hexdigest()
```

Add `content_hash` column to Review model as a **unique index** for fast dedup:

```python
class Review(Base):
    # ... existing fields ...
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    source_review_id: Mapped[str | None] = mapped_column(String(255))  # Platform's native ID
    is_processed: Mapped[bool] = mapped_column(default=False)          # Has been analyzed?
    scrape_batch_id: Mapped[str | None] = mapped_column(String(64))    # Links reviews from same scrape run
```

### 4.3 Scrape Run Tracking

```python
class ScrapeRun(Base):
    __tablename__ = "scrape_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    source: Mapped[str] = mapped_column(String(64))
    started_at: Mapped[datetime]
    completed_at: Mapped[datetime | None]
    status: Mapped[str] = mapped_column(String(32))     # "running", "completed", "failed"
    reviews_found: Mapped[int] = mapped_column(default=0)
    reviews_new: Mapped[int] = mapped_column(default=0)
    reviews_duplicate: Mapped[int] = mapped_column(default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
```

---

## 5. Implementation Phases

### Phase 1 (Current Sprint)
- [x] Fix Google Maps scraper bugs
- [x] Fix analytics pipeline (create_task, insights generation)
- [ ] Add `content_hash` to Review model for robust dedup
- [ ] Enhance analyzer prompt to extract pain points from negative reviews
- [ ] Add `pain_points` JSON field to CompanyInsight

### Phase 2 (Next Sprint)
- [ ] Implement `BaseScraper` ABC and registry
- [ ] Refactor Google Maps scraper as first plugin
- [ ] Add G2 scraper (public reviews, no auth needed)
- [ ] Add `CompanySource` model for multi-source support
- [ ] Add `ScrapeRun` tracking model

### Phase 3
- [ ] Add Capterra + Trustpilot scrapers
- [ ] Implement `AuthConfig` model and encrypted credential storage
- [ ] Build storage state capture CLI tool
- [ ] Add Celery Beat for periodic scheduling

### Phase 4
- [ ] Add review fingerprinting and cross-source dedup
- [ ] Build knowledge base accumulation (append vs overwrite insights)
- [ ] Add trend analysis (pain point changes over time)
- [ ] API: filter reviews by source, sentiment, date range
- [ ] Dashboard / reporting endpoints

---

## 6. Target Review Sites & Scraping Strategies

| Platform | Auth Required? | Strategy | Review Availability |
|---|---|---|---|
| **Google Maps** | No | Playwright — scroll + extract | Only for businesses with physical listings |
| **G2** | No (basic) / Yes (detailed) | Playwright — paginated list | ✅ All 5 target companies have G2 pages |
| **Capterra** | No | Playwright or HTTP + BS4 | ✅ Most SaaS products listed |
| **Trustpilot** | No | HTTP + JSON API (public) | Company must be registered |
| **TrustRadius** | No (basic) | Playwright | Good for enterprise SaaS |
| **Product Hunt** | No | HTTP + GraphQL API | Launch reviews only |
| **App Store / Play Store** | No | HTTP + JSON | If company has mobile app |
| **Custom/Internal** | Yes | Credential login or API token | Varies |

> **Key Insight**: For the target companies (Gallabox, AiSensy, Wati, Interakt, Zoko), **G2 and Capterra** are the primary review sources — not Google Maps. The system should prioritize these.

---

## 7. File Structure (Target State)

```
app/
├── services/
│   ├── scraping/
│   │   ├── base.py                    # BaseScraper ABC + ScrapedReview dataclass
│   │   ├── registry.py                # Plugin registry + get_scraper()
│   │   ├── playwright_helpers.py      # Browser lifecycle + utils
│   │   ├── auth_helpers.py            # Authenticated context creation
│   │   └── sources/
│   │       ├── google_maps.py
│   │       ├── g2.py
│   │       ├── capterra.py
│   │       ├── trustpilot.py
│   │       └── trustradius.py
│   ├── ai/
│   │   └── analyzer.py                # Enhanced: pain point extraction
│   ├── embeddings/
│   │   └── generator.py
│   └── insights/
│       └── generator.py               # Enhanced: negative review deep-dive
├── models/
│   ├── company.py
│   ├── company_source.py              # NEW: multi-source URLs per company
│   ├── review.py                      # Enhanced: content_hash, source_review_id
│   ├── review_analysis.py             # Enhanced: pain_points field
│   ├── company_insights.py            # Enhanced: pain_points, trend data
│   ├── scrape_run.py                  # NEW: scrape run tracking
│   └── auth_config.py                 # NEW: encrypted auth storage
├── tools/
│   └── capture_auth.py                # CLI: manual browser login → save state
└── workers/
    ├── celery_app.py                  # + Beat schedule
    └── tasks.py                       # Multi-source aware
```
