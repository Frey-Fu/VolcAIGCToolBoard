import json
import os
from fastapi.testclient import TestClient

from main_server import app

client = TestClient(app)

def test_list_modules():
    r = client.get("/api/modules")
    assert r.status_code == 200
    data = r.json()
    assert "modules" in data
    assert isinstance(data["modules"], dict)

def test_modules_detail():
    modules = client.get("/api/modules").json().get("modules", {})
    for name in modules.keys():
        r = client.get(f"/api/modules/{name}")
        assert r.status_code == 200
        data = r.json()
        assert data.get("name") == name
        assert "state" in data
