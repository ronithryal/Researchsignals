# DeFi Signal Terminal

Personal internal research tool. Monitors crypto Twitter/X, clusters posts into DeFi research signals, ranks by Research Alpha Score.

## Stack
- Backend: Python FastAPI + SQLAlchemy + Alembic + APScheduler
- Database: Postgres via Docker Compose
- X data: Apify Twitter actor (primary) / X API Basic (fallback)
- Frontend: `frontend/index.html` — static file served by FastAPI at `/`
- LLM: Codex Sonnet 4.6 (Analyst Copilot only, on-demand)

## Local dev
```bash
cp .env.example .env      # then fill in keys
docker-compose up         # starts postgres + api
# api available at http://localhost:8000
# frontend at http://localhost:8000/
```

## Testing
```bash
pytest tests/             # all tests
pytest tests/unit/        # unit only (no DB needed)
pytest tests/integration/ # needs running postgres
```

## Linting
```bash
ruff check app/ tests/ scripts/
```

## Migrations
```bash
alembic upgrade head      # apply all migrations
alembic revision --autogenerate -m "description"  # new migration
```

## Onboarding new services
```bash
python scripts/onboard_apify.py     # creates AgentMail inbox, guides signup
python scripts/onboard_anthropic.py
python scripts/onboard_dune.py      # Phase 6 only
python scripts/verify_all.py        # confirms all keys in .env work
```

## Non-negotiable constraints
- `canonical_x_url` is NOT NULL at DB, API, and frontend levels. Missing = broken state.
- Every API response that includes posts must include `canonicalXUrl` on every post.
- Analyst Copilot briefs must cite source X post URLs. Ungrounded claims labeled [HYPOTHESIS].
- Do not turn this into a tweet feed. Posts aggregate into SignalClusters, not a timeline.

## Model selection for AI coding agents
- Haiku 4.5: boilerplate, migrations, config, simple API routes, alert logic
- Sonnet 4.6: ingestion edge cases, alpha score formula, frontend integration, copilot prompts

## Key files
- `app/config.py` — all env vars with defaults
- `.env.example` — where every key goes and how to get it
- `scripts/service_registry.json` — service signup status tracker
- `app/ingestion/__init__.py` — public: `fetch_new_posts()`
- `app/scheduler.py` — APScheduler jobs (ingestion pipeline + stale-data check)
- `app/scoring/__init__.py` — public: `score_cluster(cluster_id)`
- `app/clustering/__init__.py` — public: `run_clustering(posts)`
- `app/enrichment/__init__.py` — public: `enrich_protocol(protocol_id)`
- `app/copilot/__init__.py` — public: `generate_brief(cluster_id)`

## Current phase status
- Phase 1–8: completed
- Phase 9+: pending

## Ingestion resilience knobs
- `INGESTION_HTTP_RETRIES` (default 2)
- `INGESTION_RETRY_BACKOFF_SECONDS` (default 1.0)
- `ENABLE_PROVIDER_FALLBACK` (default true)

## Skill routing

When the user's request matches an available skill, invoke it via the Skill tool. The
skill has multi-step workflows, checklists, and quality gates that produce better
results than an ad-hoc answer. When in doubt, invoke the skill. A false positive is
cheaper than a false negative.

Key routing rules:
- Bugs, errors, "why is this broken", "wtf", "this doesn't work" → invoke /investigate
- Test the site, find bugs, "does this work" → invoke /qa (or /qa-only for report only)
- Code review, check the diff, "look at my changes" → invoke /review
- Ship, deploy, create a PR, "send it" → invoke /ship
- Merge + deploy + verify → invoke /land-and-deploy
- Post-deploy monitoring → invoke /canary
- Update docs after shipping → invoke /document-release
- Security audit, OWASP, "is this secure" → invoke /cso
- Save progress, "save my work" → invoke /context-save
- Resume, restore, "where was I" → invoke /context-restore
