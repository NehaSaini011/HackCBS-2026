import hashlib
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.settings import settings

ALGORITHM = "HS256"
_DUMMY_HASH = bcrypt.hashpw(b"not-a-real-password", bcrypt.gensalt())


def check_password(password: str, stored_hash: str | None) -> bool:
    pw = password.encode()
    if len(pw) > 72:
        return False   # bcrypt only accepts up to 72 bytes; treat longer as a wrong password
    if stored_hash is None:
        # Unknown email: still spend the same time hashing, so an attacker
        # cannot tell "no such user" from "wrong password" by timing.
        bcrypt.checkpw(pw, _DUMMY_HASH)
        return False
    return bcrypt.checkpw(pw, stored_hash.encode())


def make_token(user: dict) -> str:
    now = datetime.now(timezone.utc)
    claims = {
        "sub": user["id"],                 # "subject": who this token is about
        "role": user["role"],
        "group_id": user["group_id"],
        "company_id": user["company_id"],
        "iat": now,                        # issued at
        "exp": now + timedelta(hours=settings.jwt_hours),   # expires
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=ALGORITHM)


def read_token(token: str) -> dict:
    # Raises jwt.ExpiredSignatureError or jwt.InvalidTokenError if anything is wrong.
    # algorithms=[...] is required: never let the token choose its own algorithm.
    return jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()