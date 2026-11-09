"""Entry point for uvicorn. Run from backend/ with the venv active:

    uvicorn app.main:app --reload --reload-include .env

(Settings are read once at startup; --reload-include .env restarts the server when .env changes.)

Then open http://localhost:8000/docs (interactive API docs) or http://localhost:8000/api/health.
"""

from app.factory import create_app

app = create_app()
