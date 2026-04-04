from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any

import httpx
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError

from app.core.config import settings

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class AuthContext:
    subject: str
    role: str | None
    raw: dict[str, Any]


class SupabaseTokenVerifier:
    def __init__(self) -> None:
        self._jwks: dict[str, Any] | None = None
        self._expires_at = 0.0
        self._lock = asyncio.Lock()

    async def _load_jwks(self) -> dict[str, Any]:
        async with self._lock:
            if self._jwks and time.time() < self._expires_at:
                return self._jwks

            if not settings.resolved_supabase_jwks_url:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Supabase JWKS URL is not configured.",
                )

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(settings.resolved_supabase_jwks_url)
                response.raise_for_status()
                self._jwks = response.json()
                self._expires_at = time.time() + 600
                return self._jwks

    async def verify(self, token: str) -> dict[str, Any]:
        jwks = await self._load_jwks()
        header = jwt.get_unverified_header(token)
        key = next((item for item in jwks.get("keys", []) if item.get("kid") == header.get("kid")), None)

        if not key:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown token key id.")

        public_key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(key))

        try:
            payload = jwt.decode(
                token,
                public_key,
                algorithms=[key.get("alg", "RS256")],
                audience=settings.supabase_jwt_audience,
                issuer=settings.resolved_supabase_issuer,
            )
        except InvalidTokenError as error:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token.") from error

        return payload


verifier = SupabaseTokenVerifier()


async def require_admin_access(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> AuthContext:
    admin_token = request.headers.get("x-admin-token")
    if settings.admin_api_token and admin_token == settings.admin_api_token:
        return AuthContext(subject="admin-token", role="admin", raw={"method": "admin-token"})

    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Bearer token.")

    payload = await verifier.verify(credentials.credentials)
    role = payload.get("role") or payload.get("app_metadata", {}).get("role")
    if role not in {"admin", "service_role"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required.")

    return AuthContext(subject=str(payload.get("sub")), role=role, raw=payload)
