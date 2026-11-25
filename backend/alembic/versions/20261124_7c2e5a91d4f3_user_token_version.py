"""User token version: sign out everywhere (M16)

Session tokens are stateless JWTs (L27): until now a copied token stayed valid until it expired,
even after a password change. Each token now carries the user's `token_version`; changing the
password (or "sign out everywhere") increments it, and tokens with an older version are refused.
Existing users start at 0, the version that tokens issued before this migration are read as.

Revision ID: 7c2e5a91d4f3
Revises: 0927000418b6
Create Date: 2026-11-24 19:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7c2e5a91d4f3"
down_revision: str | None = "0927000418b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("token_version", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("users", "token_version")
