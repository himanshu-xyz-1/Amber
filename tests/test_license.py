import pytest
from datetime import datetime, timedelta, timezone

from backend.app.core.license import LicenseManager
from scripts.generate_license import generate_license, DEFAULT_KEY_PATH


def test_valid_enterprise_license_verification():
    token, payload = generate_license(
        org="Test Corp",
        tier="autonomous",
        days=30,
        custom_nodes=250,
        key_path=DEFAULT_KEY_PATH
    )

    manager = LicenseManager(token=token)
    assert manager.is_valid is True
    assert manager.status == "active"
    assert manager.org == "Test Corp"
    assert manager.tier == "autonomous"
    assert manager.max_nodes == 250
    assert manager.is_feature_enabled("telegram_bot") is True
    assert manager.is_feature_enabled("whatsapp_bridge") is True
    assert manager.is_feature_enabled("slack_approvals") is True
    assert manager.days_remaining >= 29


def test_expired_license_rejection():
    # Issue license with 0 days (already expired)
    token, payload = generate_license(
        org="Expired Corp",
        tier="observe",
        days=-1,
        key_path=DEFAULT_KEY_PATH
    )

    manager = LicenseManager(token=token)
    assert manager.is_valid is False
    assert manager.status == "expired"
    assert manager.is_feature_enabled("telegram_bot") is False
    assert "expired" in manager.error_message.lower()


def test_tampered_license_rejection():
    token, payload = generate_license(
        org="Legit Corp",
        tier="autonomous",
        days=30,
        key_path=DEFAULT_KEY_PATH
    )

    # Tamper with the token characters
    tampered_token = token[:-4] + "ABCD"

    manager = LicenseManager(token=tampered_token)
    assert manager.is_valid is False
    assert manager.status == "invalid"
    assert manager.is_feature_enabled("auto_remediation") is False


def test_community_mode_when_no_token():
    manager = LicenseManager(token="")
    assert manager.is_valid is False
    assert manager.status == "community"
    assert manager.tier == "community"
    assert manager.is_feature_enabled("slack_approvals") is False
    assert manager.is_feature_enabled("whatsapp_bridge") is False
    assert manager.is_feature_enabled("telegram_bot") is False


def test_license_status_api():
    from fastapi.testclient import TestClient
    from backend.app.main import app

    client = TestClient(app)
    response = client.get("/api/v1/license/status")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "contact_url" in data
    assert "get_key_url" in data


def test_license_activate_api():
    from fastapi.testclient import TestClient
    from backend.app.main import app

    client = TestClient(app)
    headers = {"X-API-Key": "test_amber_api_key_2026"}
    # 1. Invalid key fails with 400 Bad Request
    bad_res = client.post("/api/v1/license/activate", json={"license_key": "bad_key"}, headers=headers)
    assert bad_res.status_code == 400

    # 2. Valid key succeeds
    token, _ = generate_license(
        org="API Test Corp",
        tier="response",
        days=14,
        key_path=DEFAULT_KEY_PATH
    )
    good_res = client.post("/api/v1/license/activate", json={"license_key": token}, headers=headers)
    assert good_res.status_code == 200
    assert good_res.json()["success"] is True
    assert good_res.json()["details"]["org"] == "API Test Corp"


def test_infrastructure_limits_enforcement():
    token, _ = generate_license(
        org="Scale Corp",
        tier="autonomous",
        days=30,
        custom_nodes=100,
        custom_services=20,
        key_path=DEFAULT_KEY_PATH
    )
    manager = LicenseManager(token=token)
    assert manager.is_valid is True

    # Under limit
    ok, err = manager.check_infrastructure_limits(node_count=50, service_count=10)
    assert ok is True
    assert err is None

    # Over node limit
    ok, err = manager.check_infrastructure_limits(node_count=150, service_count=10)
    assert ok is False
    assert "node limit exceeded" in err.lower()

    # Over service limit
    ok, err = manager.check_infrastructure_limits(node_count=50, service_count=25)
    assert ok is False
    assert "service limit exceeded" in err.lower()

