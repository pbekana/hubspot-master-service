import os
import time
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Ensure environment variables are available before importing app modules
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("HUBSPOT_CLIENT_ID", "test-client-id")
os.environ.setdefault("HUBSPOT_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("MINIO_ENDPOINT", "localhost:9000")
os.environ.setdefault("MINIO_ACCESS_KEY", "minio-access")
os.environ.setdefault("MINIO_SECRET_KEY", "minio-secret")
os.environ.setdefault("HMAC_ENABLED", "true")
os.environ.setdefault("HMAC_SECRET_KEY_CORE", "core-secret")
os.environ.setdefault("HMAC_SECRET_KEY_ENGINEER", "engineer-secret")
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("LOG_LEVEL", "DEBUG")

from apps.config import settings
from apps.models import base as base_model
from apps.utils import retry as retry_utils, rate_limiter as rate_limiter_utils

# Recreate the base engine and session factory for isolated SQLite testing
TEST_ENGINE = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
    future=True,
)
TEST_SESSION_LOCAL = sessionmaker(autocommit=False, autoflush=False, bind=TEST_ENGINE)
base_model.engine = TEST_ENGINE
base_model.SessionLocal = TEST_SESSION_LOCAL
base_model.Base.metadata.create_all(bind=TEST_ENGINE)

# Patch sleeps globally in tests to avoid delays
async def _noop_sleep(duration):
    return None

retry_utils.asyncio.sleep = _noop_sleep
rate_limiter_utils.asyncio.sleep = _noop_sleep


@pytest.fixture(scope="function")
def db_session():
    connection = TEST_ENGINE.connect()
    transaction = connection.begin()
    session = TEST_SESSION_LOCAL(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient
    from apps.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def hmac_headers():
    from apps.utils.security import compute_signature, hash_body, CLIENT_CONFIGS, init_hmac_clients

    init_hmac_clients()

    def _make(method: str, path: str, body: bytes = b"", client_id: str = "coordinator"):
        secret = CLIENT_CONFIGS[client_id]["secret"]
        timestamp = str(int(time.time()))
        nonce = "test-nonce"
        body_hash = hash_body(body)
        signature = compute_signature(method, path, timestamp, nonce, body_hash, secret)
        return {
            "X-HS-Client-ID": client_id,
            "X-HS-Timestamp": timestamp,
            "X-HS-Nonce": nonce,
            "X-HS-Signature": signature,
        }

    return _make
