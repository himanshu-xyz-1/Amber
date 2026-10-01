import pytest
from backend.app.core.sanitizer import (
    calculate_shannon_entropy,
    redact_string,
    sanitize_payload
)


def test_shannon_entropy_calculation():
    # Low entropy repeated string
    assert calculate_shannon_entropy("aaaaaaaaaa") < 0.1
    # Standard English text
    assert 2.5 < calculate_shannon_entropy("hello world, this is a normal sentence") < 4.2
    # High entropy cryptographic key
    assert calculate_shannon_entropy("dK9$zL@1qP8#mX4!vN7*wT2^yB5&") > 4.5


def test_redact_aws_and_github_tokens():
    raw = "Failed with key AKIAIOSFODNN7EXAMPLE and token ghp_1234567890abcdefghijklmnopqrstuvwxyz"
    sanitized = redact_string(raw)
    assert "AKIAIOSFODNN7EXAMPLE" not in sanitized
    assert "[REDACTED_AWS_KEY]" in sanitized
    assert "ghp_1234567890" not in sanitized
    assert "[REDACTED_GITHUB_TOKEN]" in sanitized


def test_redact_bearer_tokens_and_jwt():
    raw = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.doNotLeakThis"
    sanitized = redact_string(raw)
    assert "doNotLeakThis" not in sanitized
    assert "[REDACTED_TOKEN]" in sanitized or "[REDACTED_JWT]" in sanitized


def test_sanitize_nested_json_payload():
    payload = {
        "alert": "Database timeout",
        "metadata": {
            "db_url": "postgres://admin:super_secret_password_123@prod-db.internal:5432/main",
            "active_pids": [412, 415]
        },
        "user_secret": "my_hidden_api_key_value"
    }

    cleaned = sanitize_payload(payload)
    assert "super_secret_password_123" not in str(cleaned)
    assert cleaned["user_secret"] == "[REDACTED_SECRET]"
    assert cleaned["metadata"]["active_pids"] == [412, 415]
