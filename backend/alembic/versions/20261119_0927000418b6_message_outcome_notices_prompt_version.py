"""Message outcome, notices and prompt version (M13)

Saved answers need what the chat page shows next to them: whether the answer was found, not
found or stopped by the user, the notices ("no citations", "cut off", ...), and which prompt
version produced it (for evaluations). All three are new columns with safe defaults, so existing
rows (none yet: M12 didn't save answers) stay valid.

Revision ID: 0927000418b6
Revises: e0b6121b0338
Create Date: 2026-11-19 14:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0927000418b6"
down_revision: str | None = "e0b6121b0338"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("outcome", sa.String(length=20), nullable=True))
    op.add_column(
        "messages",
        sa.Column(
            "notices",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column("messages", sa.Column("prompt_version", sa.String(length=30), nullable=True))
    op.create_check_constraint(
        op.f("ck_messages_outcome"),
        "messages",
        "outcome IN ('answered', 'not_found', 'stopped')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_messages_outcome"), "messages", type_="check")
    op.drop_column("messages", "prompt_version")
    op.drop_column("messages", "notices")
    op.drop_column("messages", "outcome")
