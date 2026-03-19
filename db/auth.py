"""
Auth helpers: password hashing, JWT creation/verification.
"""

from __future__ import annotations

import os
import secrets
import sys
from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

_env_secret = os.getenv("JWT_SECRET_KEY", "").strip()
if not _env_secret or _env_secret == "CHANGE_ME_IN_PRODUCTION_USE_LONG_RANDOM_STRING":
    JWT_SECRET_KEY = secrets.token_hex(32)
    print(
        "[auth] WARNING: JWT_SECRET_KEY not set — generated a random secret for this session. "
        "All tokens will be invalidated on restart. Set JWT_SECRET_KEY env var for persistence.",
        file=sys.stderr,
    )
else:
    JWT_SECRET_KEY = _env_secret
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "24"))


# --- Password helpers ---

def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


# --- JWT helpers ---

def create_access_token(user_id: str, username: str) -> str:
    expire = datetime.utcnow() + timedelta(hours=JWT_EXPIRE_HOURS)
    payload = {
        "sub": user_id,
        "username": username,
        "exp": expire,
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    """Returns payload dict or None if invalid/expired."""
    try:
        return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except JWTError:
        return None
