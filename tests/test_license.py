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
