"""
Amber Core Security & Authentication Module.
Provides API key, Bearer JWT, and Webhook secret authentication dependencies
for REST endpoints, approvals, and dynamic license activation.
"""

import hmac
import logging
from typing import Optional

from fastapi import Depends, HTTPException, Header, Query, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from backend.app.core.config import settings

logger = logging.getLogger(__name__)

security_bearer = HTTPBearer(auto_error=False)


class AuthenticatedUser(BaseModel):
    identity: str
    role: str = "sre_admin"
    auth_method: str = "api_key"


async def require_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    x_approver_email: Optional[str] = Header(None, alias="X-Approver-Email"),
    bearer: Optional[HTTPAuthorizationCredentials] = Security(security_bearer),
) -> AuthenticatedUser:
    """
    Enforces authentication for administrative & approval REST routes.
    Accepts:
    1. 'X-API-Key: <key>' header
    2. 'Authorization: Bearer <key_or_jwt>' header
    """
    token = x_api_key or (bearer.credentials if bearer else None)

    # 1. Configured Master API Key check
    configured_key = settings.AMBER_API_KEY

    if configured_key:
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required: Missing 'X-API-Key' or 'Authorization: Bearer' header.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        # Constant-time comparison to prevent timing attacks
        if hmac.compare_digest(token.strip(), configured_key.strip()):
            approver = x_approver_email or "Authorized API Admin"
            return AuthenticatedUser(identity=approver, role="admin", auth_method="api_key")

        # Fallback: check if token is a valid JWT
        try:
            import jwt
            payload = jwt.decode(
                token,
                settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM]
            )
            sub = payload.get("sub", x_approver_email or "JWT SRE User")
            role = payload.get("role", "sre")
            return AuthenticatedUser(identity=sub, role=role, auth_method="jwt")
        except Exception:
            pass

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key or Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 2. If AMBER_API_KEY is not explicitly set in config
    if settings.ENVIRONMENT in ("development", "test"):
        approver = x_approver_email or "dev-local-sre"
        return AuthenticatedUser(identity=approver, role="admin", auth_method="dev_local")

    # In production, require AMBER_API_KEY to be configured
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Server security configuration error: AMBER_API_KEY must be configured in production.",
    )


async def require_webhook_auth(
    request: Request,
    x_webhook_secret: Optional[str] = Header(None, alias="X-Webhook-Secret"),
    token: Optional[str] = Query(None),
) -> bool:
    """
    Guards incoming webhook intake against unauthenticated spam and fake alert injection.
    Production behaviour (FAIL-CLOSED): WEBHOOK_SECRET must be configured.
    Development/test: allows unprotected webhooks for local testing.
    """
    secret = settings.WEBHOOK_SECRET

    if not secret:
        # Fail-closed in production — reject unauthenticated webhooks
        if settings.ENVIRONMENT not in ("development", "test"):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "Webhook intake is disabled: WEBHOOK_SECRET is not configured in production. "
                    "Set WEBHOOK_SECRET in your .env to enable webhook ingestion."
                ),
            )
        # Dev/test: allow without secret (log a loud warning)
        logger.warning(
            "[SECURITY] WEBHOOK_SECRET not set in development mode. "
            "All webhook intake is unauthenticated. NEVER deploy this to production."
        )
        return True

    provided_secret = x_webhook_secret or token
    if not provided_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Webhook authentication failed: Missing 'X-Webhook-Secret' header or token.",
        )

    if not hmac.compare_digest(provided_secret.strip(), secret.strip()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Webhook authentication failed: Invalid secret.",
        )

    return True

