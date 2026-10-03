import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.core.config import settings
from scripts.generate_license import generate_license, DEFAULT_KEY_PATH


def test_approvals_require_auth():
    client = TestClient(app)

    # In production with AMBER_API_KEY set
    orig_key = settings.AMBER_API_KEY
    try:
        settings.AMBER_API_KEY = "amber_prod_secret_token_123"

        # 1. Missing auth header -> 401 Unauthorized
        res_no_auth = client.get("/api/v1/approvals/pending")
        assert res_no_auth.status_code == 401
        assert "Authentication required" in res_no_auth.json()["detail"]

        # 2. Invalid auth header -> 401 Unauthorized
        res_bad_auth = client.get(
            "/api/v1/approvals/pending",
            headers={"X-API-Key": "wrong_key"}
        )
        assert res_bad_auth.status_code == 401
        assert "Invalid API Key" in res_bad_auth.json()["detail"]

        # 3. Valid X-API-Key header -> 200 OK
        res_good_key = client.get(
            "/api/v1/approvals/pending",
            headers={"X-API-Key": "amber_prod_secret_token_123"}
        )
        assert res_good_key.status_code == 200

        # 4. Valid Authorization Bearer header -> 200 OK
        res_good_bearer = client.get(
            "/api/v1/approvals/pending",
            headers={"Authorization": "Bearer amber_prod_secret_token_123"}
        )
        assert res_good_bearer.status_code == 200

        # 5. /license/activate is also guarded
        res_act_no_auth = client.post("/api/v1/license/activate", json={"license_key": "some_key"})
        assert res_act_no_auth.status_code == 401
    finally:
        settings.AMBER_API_KEY = orig_key


def test_webhook_secret_verification():
    client = TestClient(app)

    orig_secret = settings.WEBHOOK_SECRET
    try:
        settings.WEBHOOK_SECRET = "webhook_guard_secret_999"

        # 1. Missing webhook secret -> 401
        res_unauth = client.post("/api/v1/webhooks/prometheus", json={"alertname": "HighCPU"})
        assert res_unauth.status_code == 401

        # 2. Invalid webhook secret -> 401
        res_bad = client.post(
            "/api/v1/webhooks/prometheus",
            json={"alertname": "HighCPU"},
            headers={"X-Webhook-Secret": "wrong_secret"}
        )
        assert res_bad.status_code == 401

        # 3. Valid webhook secret -> 202 Accepted
        res_ok = client.post(
            "/api/v1/webhooks/prometheus",
            json={"alertname": "HighCPU"},
            headers={"X-Webhook-Secret": "webhook_guard_secret_999"}
        )
        assert res_ok.status_code == 202
    finally:
        settings.WEBHOOK_SECRET = orig_secret
