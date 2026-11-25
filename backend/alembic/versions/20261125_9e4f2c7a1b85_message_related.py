"""Related passages on a "not found" answer (M16b)

When the model finds no answer in the passages it was given, the closest of them (by semantic
score, above a measured floor) are shown with the reply, so the reader can check them. They are
saved like citations, as snapshots, in their own column: they aren't cited, so the citation
counts and "N sources cited" stay true. Existing rows get an empty list.

Revision ID: 9e4f2c7a1b85
Revises: 3b8d6e1f0a42
Create Date: 2026-11-25 16:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "9e4f2c7a1b85"
down_revision: str | None = "3b8d6e1f0a42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column(
            "related",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("messages", "related")
