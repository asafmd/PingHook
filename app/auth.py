import bcrypt
import jwt
from datetime import datetime, timezone, timedelta

from fastapi import Request
from fastapi.responses import RedirectResponse

from app.config import settings

_COOKIE = "ph_session"
_ALGO   = "HS256"
_TTL    = timedelta(days=30)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + _TTL,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=_ALGO)


def decode_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[_ALGO])
        return payload.get("sub")
    except jwt.PyJWTError:
        return None


def get_session_user_id(request: Request) -> str | None:
    token = request.cookies.get(_COOKIE)
    if not token:
        return None
    return decode_token(token)


def login_response(user_id: str, redirect_to: str = "/dashboard") -> RedirectResponse:
    token    = create_token(user_id)
    response = RedirectResponse(url=redirect_to, status_code=303)
    response.set_cookie(
        key=_COOKIE,
        value=token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=int(_TTL.total_seconds()),
        path="/",
    )
    return response


def logout_response() -> RedirectResponse:
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie(_COOKIE, path="/")
    return response
