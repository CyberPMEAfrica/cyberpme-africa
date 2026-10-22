"""CI-only security regression on a disposable PostgreSQL database."""
import os
from pathlib import Path
import sys
import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root), str(root/'tests')]
url = os.environ['TEST_POSTGRES_URL']
if not os.environ.get('CI'):
    raise SystemExit('CI-only runner: refusing to drop tables outside a disposable CI database.')
parsed = make_url(url)
if parsed.host not in {'localhost', '127.0.0.1'} or parsed.database != 'security_ci' or parsed.username != 'security_ci':
    raise SystemExit('Refusing non-local or non-disposable security test database.')
import test_api
import app.database as database
engine = create_engine(url)
database.engine = engine
database.SessionLocal.configure(bind=engine)
test_api.engine = engine
raise SystemExit(pytest.main(['-q', str(root/'tests/test_security.py'), str(root/'tests/test_managed_actions.py')]))
