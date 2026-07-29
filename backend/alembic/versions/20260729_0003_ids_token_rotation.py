"""support safe IDS connector token rotation

Revision ID: 20260729_0003
Revises: 20260729_0002
Create Date: 2026-07-29
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260729_0003"
down_revision: Union[str, Sequence[str], None] = "20260729_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("ids_connectors") as batch_op:
        batch_op.add_column(
            sa.Column("previous_token_hash", sa.String(length=64), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "previous_token_expires_at",
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column("token_rotated_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.create_index(
            "ix_ids_connectors_previous_token_hash",
            ["previous_token_hash"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("ids_connectors") as batch_op:
        batch_op.drop_index("ix_ids_connectors_previous_token_hash")
        batch_op.drop_column("token_rotated_at")
        batch_op.drop_column("previous_token_expires_at")
        batch_op.drop_column("previous_token_hash")
