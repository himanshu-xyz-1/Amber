"""
Pytest global configuration and fixtures.
Ensures ENVIRONMENT is always 'test' during test execution.
"""

import os
import pytest

# Enforce test environment before any application imports
os.environ["ENVIRONMENT"] = "test"
if not os.environ.get("AMBER_API_KEY"):
    os.environ["AMBER_API_KEY"] = "test_amber_api_key_2026"
if not os.environ.get("JWT_SECRET_KEY"):
    os.environ["JWT_SECRET_KEY"] = "test_jwt_secret_key_for_unit_tests"


@pytest.fixture(autouse=True)
def enforce_test_env(monkeypatch):
    """Guarantees test environment isolation for all test cases."""
    monkeypatch.setenv("ENVIRONMENT", "test")
