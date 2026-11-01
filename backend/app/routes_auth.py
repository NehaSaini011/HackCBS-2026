from fastapi import APIRouter, Depends, HTTPException

from app import yb
from app.deps import User, current_user
from app.models import LoginIn
from app.security import check_password, make_token

router = APIRouter()

USER_SQL = ("SELECT u.id, u.email, u.role, u.group_id, u.company_id, u.password_hash, "
            "c.name AS company_name FROM users u "
            "LEFT JOIN companies c ON c.id = u.company_id ")


def user_json(row: dict) -> dict:
    """The user as contract C7 shows it. Never includes the password hash."""
    company = {"id": row["company_id"], "name": row["company_name"]} if row["company_id"] else None
    return {"id": row["id"], "email": row["email"], "role": row["role"],
            "group_id": row["group_id"], "company": company}


@router.post("/auth/login")
def login(body: LoginIn):
    row = yb.q1(USER_SQL + "WHERE lower(u.email) = lower(%s)", (body.email.strip(),))
    if not check_password(body.password, row["password_hash"] if row else None):
        # Same message for unknown email and wrong password: don't reveal which.
        raise HTTPException(401, "Wrong email or password")
    return {"token": make_token(row), "user": user_json(row)}


@router.get("/me")
def me(user: User = Depends(current_user)):
    row = yb.q1(USER_SQL + "WHERE u.id = %s", (user.id,))
    return user_json(row)