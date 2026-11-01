from dataclasses import dataclass

import jwt
from fastapi import Depends, Header, HTTPException

from app import yb
from app.security import hash_key, read_token


@dataclass
class User:
    id: str
    email: str
    role: str
    group_id: str
    company_id: str | None


@dataclass
class Company:
    id: str
    group_id: str
    name: str
    shop: str | None


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing Authorization: Bearer header")
    return authorization.removeprefix("Bearer ").strip()


def current_user(authorization: str | None = Header(default=None)) -> User:
    """Any logged-in person."""
    token = _bearer(authorization)
    try:
        claims = read_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Session expired, log in again")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid token")
    # Load from the database, so a deleted user or changed role takes effect at once
    row = yb.q1("SELECT id, email, role, group_id, company_id FROM users WHERE id = %s",
                (claims["sub"],))
    if not row:
        raise HTTPException(401, "User no longer exists")
    return User(**row)


def engineer(user: User = Depends(current_user)) -> User:
    """Only a company engineer."""
    if user.role != "engineer" or not user.company_id:
        raise HTTPException(403, "Company engineers only")
    return user


def group_admin(user: User = Depends(current_user)) -> User:
    """Only the group admin."""
    if user.role != "group_admin":
        raise HTTPException(403, "Group admin only")
    return user


def company_from_key(authorization: str | None = Header(default=None)) -> Company:
    """A machine (Alertmanager, adapters, agent): which company does this key belong to?"""
    key = _bearer(authorization)
    row = yb.q1(
        "SELECT c.id, c.group_id, c.name, c.shop FROM api_keys k "
        "JOIN companies c ON c.id = k.company_id WHERE k.key_hash = %s",
        (hash_key(key),))
    if not row:
        raise HTTPException(401, "Unknown API key")
    return Company(**row)