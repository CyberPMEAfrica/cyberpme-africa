"""Additive security controls. No monitoring data is deleted."""
from datetime import datetime, timedelta, timezone
from alembic import op
import sqlalchemy as sa

revision = "20261022_0007"
down_revision = "20260924_0006"
branch_labels = None
depends_on = None


def upgrade():
    from app.security_models import AccountSecurity, AuthRateBucket, AgentSecurity, EnrollmentPolicy
    bind = op.get_bind()
    for model in (AccountSecurity, AuthRateBucket, AgentSecurity, EnrollmentPolicy):
        model.__table__.create(bind, checkfirst=True)
    # Existing paired scanners retain their capability for a bounded transition.
    # They must be re-paired explicitly in monitoring mode before a client pilot.
    security = AgentSecurity.__table__
    rows = bind.execute(sa.text("SELECT c.server_id, s.network_scan_capable FROM agent_credentials c JOIN servers s ON s.id=c.server_id")).all()
    for server_id, capable in rows:
        # raw SQLite UUIDs differ from PostgreSQL's UUID objects
        from uuid import UUID
        ident = server_id if isinstance(server_id, UUID) else UUID(str(server_id))
        if not bind.execute(sa.select(security.c.server_id).where(security.c.server_id == ident)).first():
            now = datetime.now(timezone.utc)
            bind.execute(security.insert().values(server_id=ident, mode="network" if capable else "monitoring", expires_at=now + timedelta(days=90), rotated_at=now))


def downgrade():
    raise RuntimeError("Security downgrade requires a reviewed recovery procedure; use a forward migration.")
