import os

import pymongo
import pytest

# Must be set before matini.api.core.config is imported. A dedicated *_test database is
# used, and only that database is ever cleaned.
TEST_MONGODB_URI = os.getenv("TEST_MONGODB_URI", "mongodb://localhost:27017/matinidb_test")
os.environ["MONGODB_URI"] = TEST_MONGODB_URI


def _mongo_available() -> bool:
    try:
        client = pymongo.MongoClient(TEST_MONGODB_URI, serverSelectionTimeoutMS=1500)
        client.admin.command("ping")
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def api_client():
    """FastAPI client with the lifespan (Beanie init) running against the test database."""
    if not _mongo_available():
        pytest.skip(f"MongoDB not reachable at {TEST_MONGODB_URI} (set TEST_MONGODB_URI)")

    from fastapi.testclient import TestClient
    from matini.api import create_application

    sync_client = pymongo.MongoClient(TEST_MONGODB_URI)
    db = sync_client.get_default_database()
    assert db.name.endswith("_test"), f"refusing to clean non-test database {db.name!r}"
    sync_client.drop_database(db.name)

    with TestClient(create_application()) as client:
        yield client

    sync_client.drop_database(db.name)
