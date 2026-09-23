"""Queue private network scans for an on-premise agent.

Revision ID: 20260922_0005
Revises: 20260922_0004
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260922_0005"
down_revision: Union[str, Sequence[str], None] = "20260922_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "network_scan_capable" not in {c["name"] for c in inspector.get_columns("servers")}:
        with op.batch_alter_table("servers") as batch_op:
            batch_op.add_column(sa.Column("network_scan_capable", sa.Boolean(), nullable=False, server_default=sa.false()))
    if "agent_enrollment_tokens" not in inspector.get_table_names():
        create_enrollment_table()
    if "agent_server_id" in {c["name"] for c in inspector.get_columns("network_scans")}:
        return
    with op.batch_alter_table("network_scans") as batch_op:
        batch_op.add_column(sa.Column("agent_server_id", sa.Uuid(), nullable=True))
        batch_op.create_index("ix_network_scans_agent_server_id", ["agent_server_id"])
        batch_op.create_foreign_key("fk_network_scans_agent_server_id_servers", "servers", ["agent_server_id"], ["id"], ondelete="SET NULL")


def create_enrollment_table() -> None:
    op.create_table(
        "agent_enrollment_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_by_email", sa.String(length=254), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_enrollment_tokens_organization_id", "agent_enrollment_tokens", ["organization_id"])
    op.create_index("ix_agent_enrollment_tokens_token_hash", "agent_enrollment_tokens", ["token_hash"], unique=True)
    op.create_index("ix_agent_enrollment_tokens_expires_at", "agent_enrollment_tokens", ["expires_at"])


def downgrade() -> None:
    with op.batch_alter_table("servers") as batch_op:
        batch_op.drop_column("network_scan_capable")
    with op.batch_alter_table("network_scans") as batch_op:
        batch_op.drop_constraint("fk_network_scans_agent_server_id_servers", type_="foreignkey")
        batch_op.drop_index("ix_network_scans_agent_server_id")
        batch_op.drop_column("agent_server_id")
    op.drop_index("ix_agent_enrollment_tokens_expires_at", table_name="agent_enrollment_tokens")
    op.drop_index("ix_agent_enrollment_tokens_token_hash", table_name="agent_enrollment_tokens")
    op.drop_index("ix_agent_enrollment_tokens_organization_id", table_name="agent_enrollment_tokens")
    op.drop_table("agent_enrollment_tokens")
