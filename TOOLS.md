# TOOLS.md - Vidya

## Plugins

Install using /plugin inside Claude Code at USER scope.

superpowers:
Brainstorm, write plan, execute plan.

code-simplifier:
Post-implementation cleanup.

context7:
Live API documentation for FastAPI, SQLAlchemy, Celery, React, Gemini.

context-mode:
Context savings for large outputs, if available.

## MCPs

filesystem:
Read project files without pasting.

memory:
Persist decisions, open questions, and schema changes.

sequential-thinking:
Architecture and debugging chains.

## Session Launcher

.\vidya-sessions.ps1 -Session list
.\vidya-sessions.ps1 -Session auth
.\vidya-sessions.ps1 -Session audit
.\vidya-sessions.ps1 -Session debug
.\vidya-sessions.ps1 -Session status

## Docker

docker compose up -d
docker compose logs -f vidya-api
docker compose exec vidya-api bash

## Database

alembic upgrade head
alembic revision --autogenerate -m "desc"

## Tests

cd backend
pytest -v
pytest tests/test_auth.py -v
pytest --cov=app tests/

## Celery

celery -A app.workers.celery_app worker --loglevel=info
celery -A app.workers.celery_app flower
