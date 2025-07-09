import os
import sys
import types
import pytest
from fastapi.testclient import TestClient

# Ensure environment variables exist for app import
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_KEY", "testkey")

import app

client = TestClient(app.app)

def test_get_api():
    response = client.get("/api")
    assert response.status_code == 200
    assert response.json() == {"message": "Welcome to MenuLens API!"}

def test_user_profile_no_token():
    response = client.post("/api/user/profile")
    assert response.status_code == 401

def test_user_profile_with_token(monkeypatch):
    def mock_get_user(token):
        return types.SimpleNamespace(user=types.SimpleNamespace(id="123"))

    class DummyQuery:
        def select(self, *args, **kwargs):
            return self
        def eq(self, *args, **kwargs):
            return self
        def single(self):
            return self
        def execute(self):
            return types.SimpleNamespace(data={
                "id": "123",
                "first_name": "John",
                "last_name": "Doe",
                "email": "john@example.com",
                "birthday": "2000-01-01",
                "gender": "male",
                "credits": 10,
            })

    monkeypatch.setattr(app.supabase.auth, "get_user", mock_get_user)
    monkeypatch.setattr(app.supabase, "from_", lambda *args, **kwargs: DummyQuery())

    headers = {"Authorization": "Bearer validtoken"}
    response = client.post("/api/user/profile", headers=headers)
    assert response.status_code == 200
    assert response.json() == {
        "first_name": "John",
        "last_name": "Doe",
        "email": "john@example.com",
        "birthday": "2000-01-01",
        "gender": "male",
        "credits": 10,
    }
