from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.demo_seed import seed_demo_data
from app.models import (
    Alert,
    BackupCheck,
    Metric,
    NetworkScan,
    Organization,
    SecurityEvent,
    Server,
    SslCheck,
)


def test_demo_seed_populates_all_dashboard_sections_once():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as db:
        organization = Organization(name="CyberPME Démonstration", slug="cyberpme-demo")
        db.add(organization)
        db.commit()
        db.refresh(organization)

        assert seed_demo_data(db, organization) is True
        counts = {
            Server: 3,
            Metric: 12,
            Alert: 2,
            NetworkScan: 2,
            SslCheck: 2,
            BackupCheck: 3,
            SecurityEvent: 4,
        }
        for model, expected in counts.items():
            assert db.scalar(select(func.count()).select_from(model)) == expected

        assert seed_demo_data(db, organization) is False
        for model, expected in counts.items():
            assert db.scalar(select(func.count()).select_from(model)) == expected
