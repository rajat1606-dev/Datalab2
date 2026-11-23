"""Pytest fixtures: isolated SQLite DB per test session + API test client."""
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """FastAPI TestClient bound to a throwaway database."""
    import database
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "test-datalab.db")
    database.init_db()

    import main
    from fastapi.testclient import TestClient
    with TestClient(main.app) as tc:
        yield tc


DIRTY_CSV = """Date,Region,Sales,Product
2024-01-15,North,120,A
15/02/2024, north ,250.5,b
2024-01-15,North,120,A
2024-03-10,South,N/A,C
2024-04-01,North,99999,A
2024-04-02,East,,B
2024-04-03,west,95.5,c
2024-04-04,East,88.0,B
2024-04-05,East,88.0,B
2024-04-06,South,110,C
"""


@pytest.fixture()
def dirty_dataset(client):
    """Upload the standard dirty CSV and return its dataset id."""
    resp = client.post(
        "/api/cleanflow/datasets/upload",
        files={"file": ("dirty.csv", DIRTY_CSV.encode())},
        data={"name": "Dirty Demo"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]
