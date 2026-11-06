"""Qdrant access. M2 only builds the client; collections, upserts and search arrive in M9."""

from __future__ import annotations

from qdrant_client import QdrantClient

from app.core.config import Settings


def build_qdrant_client(settings: Settings) -> QdrantClient:
    api_key = settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key else None
    return QdrantClient(
        url=settings.qdrant_url,
        api_key=api_key,
        timeout=30,
        # By default the client calls the server while being constructed, to compare versions.
        # That would put a network call (~260 ms) inside app startup and inside every test that
        # builds the app. pyproject pins the client to the server's minor version (1.20) instead.
        check_compatibility=False,
    )
