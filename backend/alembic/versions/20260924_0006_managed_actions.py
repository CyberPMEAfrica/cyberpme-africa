"""Approved local backup, restore test and temporary firewall operations."""
from alembic import op
import sqlalchemy as sa

revision = '20260924_0006'
down_revision = '20260922_0005'
branch_labels = None
depends_on = None


def upgrade():
    # Legacy installations may already have tables created by metadata.create_all.
    if 'managed_actions' in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table('managed_actions',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('organization_id', sa.Uuid(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('server_id', sa.Uuid(), sa.ForeignKey('servers.id'), nullable=False),
        sa.Column('kind', sa.String(24), nullable=False),
        sa.Column('status', sa.String(24), nullable=False),
        sa.Column('profile', sa.String(64)), sa.Column('snapshot', sa.String(64)),
        sa.Column('source_ip', sa.String(45)),
        sa.Column('event_id', sa.Uuid(), sa.ForeignKey('security_events.id')),
        sa.Column('parent_id', sa.Uuid(), sa.ForeignKey('managed_actions.id')),
        sa.Column('duration_minutes', sa.Integer(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('proposed_by', sa.String(254), nullable=False),
        sa.Column('approved_by', sa.String(254)),
        *[sa.Column(n, sa.DateTime(timezone=True), nullable=n!='created_at') for n in
          ('created_at','approved_at','expires_at','started_at','completed_at')],
        sa.Column('result', sa.JSON(), nullable=False))
    for name in ('organization_id','server_id','status'):
        op.create_index('ix_managed_actions_'+name, 'managed_actions', [name])


def downgrade():
    op.drop_table('managed_actions')
