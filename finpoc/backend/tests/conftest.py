import os
import tempfile

_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["DATABASE_URL"] = f"sqlite:///{_db.name}"
os.environ["SEED_DEMO_DATA"] = "true"
os.environ.pop("AZURE_OPENAI_API_KEY", None)
os.environ.pop("ANTHROPIC_API_KEY", None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services.seed import DEMO_PASSWORD  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def tokens(client):
    out = {}
    for user in ["admin", "analyst", "finance", "compliance", "auditor"]:
        resp = client.post("/api/auth/login", data={"username": user, "password": DEMO_PASSWORD})
        assert resp.status_code == 200, resp.text
        out[user] = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    return out
