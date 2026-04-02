"""JWT authentication and enterprise context injection."""

from dataclasses import dataclass, field

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.config import settings

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class EnterpriseContext:
    """Injected into every endpoint via Depends(get_enterprise_context)."""

    enterprise_id: str
    user_id: str | None = None
    email: str | None = None
    roles: list[str] = field(default_factory=list)


def _decode_jwt(token: str) -> dict:
    try:
        return jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def _context_from_payload(payload: dict) -> EnterpriseContext:
    enterprise_id = payload.get("enterprise_id")
    if not enterprise_id:
        raise HTTPException(status_code=401, detail="Missing enterprise_id in token")
    return EnterpriseContext(
        enterprise_id=enterprise_id,
        user_id=payload.get("sub"),
        email=payload.get("email"),
        roles=payload.get("roles", []),
    )


async def get_enterprise_context(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> EnterpriseContext:
    """FastAPI dependency that extracts enterprise context from the request.

    Resolution order:
    1. Authorization: Bearer <jwt>
    2. Dev mode — default enterprise context (no auth required)
    """
    # 1. Standard Bearer token
    if credentials:
        return _context_from_payload(_decode_jwt(credentials.credentials))

    # 2. Dev mode bypass
    if settings.auth_dev_mode:
        enterprise_id = request.headers.get("x-enterprise-id", "dev-enterprise")
        return EnterpriseContext(
            enterprise_id=enterprise_id,
            user_id="dev-user",
        )

    raise HTTPException(status_code=401, detail="Missing authentication")
