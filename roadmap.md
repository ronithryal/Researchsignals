---
name: Implementation Roadmap
description: All phases with recommended models — updated 2026-04-24
type: project
originSessionId: e4f313f4-e654-421b-9b98-fea7e450bb4e
---
## Model Tiers (available)

| Tier | Models | Best for |
|---|---|---|
| **Top** | Opus 4.7, Gemini 2.5 Pro | Complex architecture, hard debugging, long-context frontend |
| **Balanced** | Sonnet 4.6 | Core logic, module integration, copilot prompts, frontend wiring |
| **Fast** | Haiku 4.5, Gemini Flash | Simple routes, boilerplate, scheduling, logging, docs |
| **Ultra-cheap** | Qwen, Deepseek, Kimi | Config files, migrations, unit test scaffolding, Docker |

---

## Phase Roadmap

| # | What | Status | Recommended Model | Notes |
|---|---|---|---|---|
| **1** | Project scaffold — Dockerfile, docker-compose, FastAPI skeleton, `frontend/index.html`, scripts | ✅ Done | Haiku 4.5 | Boilerplate |
| **2** | Database — 8 SQLAlchemy models, Alembic config, initial migration, `.env.example` | ✅ Done | Haiku 4.5 | Schema design done |
| **3** | Core modules — `fetch_new_posts`, `run_clustering`, `score_cluster`, `enrich_protocol`, `generate_brief` | ✅ Done | Sonnet 4.6 | Done this session |
| **4** | FastAPI routes — `/api/posts`, `/api/clusters`, `/api/clusters/{id}/brief`, `/api/protocols/{id}`, `/api/alerts`, `/api/ingestion/status` | ✅ Done | Sonnet 4.6 (routes) / Haiku 4.5 (alert CRUD) | Module wiring needs judgment |
| **5** | Frontend UI — static HTML dashboard: top clusters by alpha score, cluster detail, protocol search, alert config | ✅ Done | Sonnet 4.6 or Gemini 2.5 Pro | Wired UI to FastAPI backend endpoints |
| **6** | APScheduler — ingestion every 30 min, clustering + scoring pipeline, stale-data alert after 120 min | ⬜ | Haiku 4.5 (job wiring) / Sonnet 4.6 (alert logic) | Scheduling boilerplate is cheap; alert conditions need care |
| **7** | Tests — unit (scoring formula, clustering logic, no DB) + integration (Postgres: ingestion, copilot) | ⬜ | Qwen/Deepseek (unit) / Haiku 4.5 (integration) | Unit tests are formulaic; integration needs DB awareness |
| **8** | Error handling & retry logic — httpx retries, ingestion fallback, partial failure recovery | ⬜ | Haiku 4.5 | Well-defined patterns |
| **9** | Logging & monitoring — structured logs, IngestionRun dashboard, stale-data alerts | ⬜ | Gemini Flash | Config + boilerplate |
| **10** | Docker Compose refinement — healthchecks, volume mounts, env wiring | ⬜ | Qwen/Deepseek | Pure config |
| **11** | Deployment docs — README, runbook, `.env.example` completion | ⬜ | Gemini Flash | Writing task |

---

## When to escalate to Opus 4.7

- Debugging hard async/ORM bugs across multiple modules
- Designing the Dune analytics integration (Phase 6 enrichment expansion)
- Security or correctness review before any production deploy
- Whenever Sonnet produces wrong output after 1–2 retries

## When to use Gemini 2.5 Pro

- Phase 5 frontend if the full HTML/JS exceeds ~600 lines (long-context advantage)
- Reviewing a large diff spanning many files at once
