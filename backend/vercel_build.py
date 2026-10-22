"""Production-only, additive schema upgrade before Vercel switches traffic."""
import os
from pathlib import Path


def main():
    if os.environ.get('VERCEL_ENV') != 'production':
        print('Preview: no database migration performed.')
        return
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, text
    from app.config import settings
    from app.security_preflight import validate_production_security
    validate_production_security()

    engine = create_engine(settings.database_url)
    try:
        with engine.connect() as connection:
            revision = connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one()
        if revision not in ('20260922_0005', '20260924_0006', '20261022_0007'):
            raise RuntimeError('Unexpected database revision; manual migration review required.')
    except Exception:
        raise RuntimeError('Database preflight failed. Deployment stopped; review database access and migration revision.') from None
    finally:
        engine.dispose()
    config = Config(str(Path(__file__).with_name('alembic.ini')))
    command.upgrade(config, 'head')
    print('Production schema ready: 20261022_0007.')


if __name__ == '__main__':
    main()
