"""Conversations across all knowledge bases (M16b)

A conversation either belongs to one knowledge base (as before) or, with `kb_id` NULL, asks
across every knowledge base its owner has. The foreign key and its ON DELETE CASCADE stay:
deleting a knowledge base still deletes its own conversations, and an all-knowledge-base
conversation keeps its saved answers (their citations are snapshots).

Revision ID: 3b8d6e1f0a42
Revises: 7c2e5a91d4f3
Create Date: 2026-11-25 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3b8d6e1f0a42"
down_revision: str | None = "7c2e5a91d4f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("conversations", "kb_id", existing_type=sa.Uuid(), nullable=True)


def downgrade() -> None:
    # All-knowledge-base conversations have nowhere to go in the old schema.
    op.execute("DELETE FROM conversations WHERE kb_id IS NULL")
    op.alter_column("conversations", "kb_id", existing_type=sa.Uuid(), nullable=False)
