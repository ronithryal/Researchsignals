# GritHunter: DeFi Signal Terminal

Personal internal research tool for monitoring crypto Twitter/X, clustering posts into DeFi research signals, and ranking them by Research Alpha Score.

## Stack
- **Backend**: Python FastAPI + SQLAlchemy + Alembic + APScheduler
- **Database**: Postgres via Docker Compose
- **X Data**: Apify Twitter actor (primary) / X API Basic (fallback)
- **Frontend**: Static HTML/JS dashboard served by FastAPI at `/`
- **LLM**: Claude Sonnet 3.5 (Analyst Copilot)

## Local Development

### Prerequisites
- Docker & Docker Compose
- Python 3.12 (for local development without Docker)

### Setup
1. Clone the repository.
2. Create a `.env` file from `.env.example`:
   ```bash
   cp .env.example .env
   ```
3. Fill in the required API keys (Apify, Anthropic, X API).
4. Start the services:
   ```bash
   docker-compose up --build
   ```
5. Access the terminal at [http://localhost:8000/](http://localhost:8000/).
6. Access API documentation at [http://localhost:8000/docs](http://localhost:8000/docs).

## Project Structure
- `app/`: Core application logic
  - `ingestion/`: Fetching posts from X
  - `clustering/`: Grouping posts into signals
  - `scoring/`: Calculating Research Alpha Scores
  - `enrichment/`: Protocol-level metadata
  - `copilot/`: Analyst brief generation via LLM
  - `scheduler.py`: Background job management
- `frontend/`: Static frontend assets
- `scripts/`: Service onboarding and verification scripts
- `tests/`: Unit and integration test suites

## Maintenance
- **Linting**: `ruff check app/ tests/`
- **Testing**: `pytest tests/`
- **Migrations**: `alembic upgrade head`
- **Logs**: JSON structured logs in production (`JSON_LOGS=True`)

## Non-negotiable constraints
- `canonical_x_url` is mandatory for all posts.
- Analyst Copilot briefs must cite source X post URLs.
- Data is aggregated into SignalClusters, not displayed as a raw tweet feed.
