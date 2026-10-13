"""Login and signed bearer tokens (JWT layout, HS256 via stdlib ``hmac``).

The tenant (``chain_id``) and the role always come from the verified token, never from a request body.

Roles:
* ``owner``: every store of the token's chain; can approve/reject/edit every draft of the chain.
* ``store_manager``: only ``store_id`` of the token. Any request naming another store gets 403
  ``forbidden_store``; drafts, audit entries and store lists are filtered to that store.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import asdict, dataclass

from fastapi import Request

from api.errors import ApiError
from data_sim import CHAIN_IDS, chain_db_path, open_chain_db
from data_sim.auth import hash_password, verify_password


@dataclass(frozen=True)
class User:
    user_id: str
    username: str
    role: str  # "owner" | "store_manager"
    chain_id: str
    store_id: str | None

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def is_owner(self) -> bool:
        return self.role == "owner"


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(secret: str, signing_input: str) -> str:
    return _b64(hmac.new(secret.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest())


def issue_token(user: User, secret: str, ttl_s: int, *, now: float | None = None) -> str:
    iat = int(now if now is not None else time.time())
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    claims = {**user.to_dict(), "sub": user.user_id, "iat": iat, "exp": iat + int(ttl_s)}
    payload = _b64(json.dumps(claims, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    return f"{header}.{payload}.{_sign(secret, f'{header}.{payload}')}"


_BAD_TOKEN = ApiError(401, "invalid_token", "Phiên đăng nhập không hợp lệ. Vui lòng đăng nhập lại.")


def verify_token(token: str, secret: str, *, now: float | None = None) -> User:
    parts = token.split(".")
    if len(parts) != 3:
        raise _BAD_TOKEN
    header, payload, signature = parts
    if not hmac.compare_digest(_sign(secret, f"{header}.{payload}"), signature):
        raise _BAD_TOKEN
    try:
        if json.loads(_unb64(header)).get("alg") != "HS256":
            raise _BAD_TOKEN
        claims = json.loads(_unb64(payload))
        user = User(
            claims["user_id"], claims["username"], claims["role"], claims["chain_id"], claims.get("store_id")
        )
        exp = int(claims["exp"])
    except (ValueError, KeyError, TypeError):
        raise _BAD_TOKEN from None
    if user.chain_id not in CHAIN_IDS or user.role not in ("owner", "store_manager"):
        raise _BAD_TOKEN
    if (now if now is not None else time.time()) >= exp:
        raise ApiError(401, "token_expired", "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.")
    return user


_DUMMY_HASH = hash_password("freshmesh-dummy-password")


def authenticate(data_dir, username: str, password: str) -> User:
    """Find the user in the chain databases and check the PBKDF2 password hash."""
    for chain_id in CHAIN_IDS:
        if not chain_db_path(data_dir, chain_id).exists():
            continue
        con = open_chain_db(data_dir, chain_id, readonly=True)
        try:
            row = con.execute(
                "SELECT user_id, username, role, chain_id, store_id, password_hash FROM users "
                "WHERE username = ?",
                (username,),
            ).fetchone()
        finally:
            con.close()
        if row is not None:
            if verify_password(password, row["password_hash"]) and row["chain_id"] == chain_id:
                return User(row["user_id"], row["username"], row["role"], row["chain_id"], row["store_id"])
            break
    else:
        verify_password(password, _DUMMY_HASH)  # equalise timing so unknown usernames are not revealed
    raise ApiError(401, "invalid_credentials", "Tên đăng nhập hoặc mật khẩu không đúng.")


def current_user(request: Request) -> User:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise ApiError(401, "unauthorized", "Bạn cần đăng nhập (thiếu mã xác thực).")
    return verify_token(token.strip(), request.app.state.settings.secret)
