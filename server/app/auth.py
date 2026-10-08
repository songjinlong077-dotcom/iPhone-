from __future__ import annotations

import hashlib
import secrets

from fastapi import Header, HTTPException, status


class ApiKeyAuth:
    def __init__(self, api_key: str) -> None:
        self._digest = hashlib.sha256(api_key.encode("utf-8")).digest()

    def __call__(self, authorization: str | None = Header(default=None)) -> None:
        scheme, _, token = (authorization or "").partition(" ")
        supplied = hashlib.sha256(token.encode("utf-8")).digest()
        if scheme.lower() != "bearer" or not token or not secrets.compare_digest(supplied, self._digest):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="无效或缺失的 API Key。",
                headers={"WWW-Authenticate": "Bearer"},
            )
