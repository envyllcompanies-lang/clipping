import os

import pytest

os.environ.setdefault("TOKEN_ENCRYPTION_KEY", "test-key-not-secret")
TEST_DB = os.environ.get("TEST_DATABASE_URL", "postgresql:///clipping_test")


@pytest.fixture(scope="session")
def _schema():
    import psycopg

    from clipping.core import db

    db.set_url(TEST_DB)
    with psycopg.connect(TEST_DB, autocommit=True) as c:
        c.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        db.migrate(c)
    yield


@pytest.fixture
def conn(_schema):
    from clipping.core import db

    c = db.connect()
    tables = [r["tablename"] for r in c.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename<>'schema_version'")]
    c.execute("TRUNCATE " + ",".join(f'"{t}"' for t in tables) + " RESTART IDENTITY CASCADE")
    yield c
    c.close()


@pytest.fixture
def tmp_data(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPPING_DATA_DIR", str(tmp_path))
    return tmp_path
