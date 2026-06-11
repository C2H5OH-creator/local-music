import base64
import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from fastapi import Request
from psycopg import errors

from api.db import get_connection
from api.settings import get_settings


SESSION_COOKIE_NAME = "local_music_session"
SESSION_TTL_SECONDS = 60 * 60 * 24 * 30
PASSWORD_ITERATIONS = 240_000


@dataclass(frozen=True)
class CurrentUser:
    id: str
    username: str


class AuthError(ValueError):
    pass


class DuplicateUserError(AuthError):
    pass


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_ITERATIONS,
    )
    return "$".join(
        [
            "pbkdf2_sha256",
            str(PASSWORD_ITERATIONS),
            base64.urlsafe_b64encode(salt).decode("ascii"),
            base64.urlsafe_b64encode(digest).decode("ascii"),
        ]
    )


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt_text, digest_text = password_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_text)
        salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        expected_digest = base64.urlsafe_b64decode(digest_text.encode("ascii"))
    except (ValueError, TypeError):
        return False

    actual_digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(actual_digest, expected_digest)


def create_user(username: str, password: str) -> CurrentUser:
    username = normalize_username(username)
    validate_password(password)

    with get_connection() as connection:
        try:
            row = connection.execute(
                """
                INSERT INTO users (username, password_hash)
                VALUES (%s, %s)
                RETURNING id, username
                """,
                (username, hash_password(password)),
            ).fetchone()
        except errors.UniqueViolation as error:
            raise DuplicateUserError("Пользователь с таким логином уже существует") from error

    return row_to_user(row)


def authenticate_user(username: str, password: str) -> CurrentUser:
    username = normalize_username(username)

    with get_connection() as connection:
        row = connection.execute(
            "SELECT id, username, password_hash FROM users WHERE username = %s",
            (username,),
        ).fetchone()

    if row is None or not verify_password(password, row["password_hash"]):
        raise AuthError("Неверный логин или пароль")

    return row_to_user(row)


def get_user_by_id(user_id: str) -> CurrentUser | None:
    try:
        UUID(user_id)
    except ValueError:
        return None

    with get_connection() as connection:
        row = connection.execute(
            "SELECT id, username FROM users WHERE id = %s",
            (user_id,),
        ).fetchone()

    if row is None:
        return None
    return row_to_user(row)


def get_current_user(request: Request) -> CurrentUser | None:
    session = request.cookies.get(SESSION_COOKIE_NAME)
    if not session:
        return None

    user_id = verify_session_token(session)
    if user_id is None:
        return None

    return get_user_by_id(user_id)


def create_session_token(user_id: str) -> str:
    expires_at = int(time.time()) + SESSION_TTL_SECONDS
    payload = f"{user_id}:{expires_at}"
    signature = sign_payload(payload)
    token = f"{payload}:{signature}"
    return base64.urlsafe_b64encode(token.encode("utf-8")).decode("ascii")


def verify_session_token(token: str) -> str | None:
    try:
        decoded = base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8")
        user_id, expires_at_text, signature = decoded.rsplit(":", 2)
        payload = f"{user_id}:{expires_at_text}"
        expires_at = int(expires_at_text)
    except (ValueError, UnicodeDecodeError):
        return None

    if expires_at < int(time.time()):
        return None

    expected_signature = sign_payload(payload)
    if not hmac.compare_digest(signature, expected_signature):
        return None

    return user_id


def sign_payload(payload: str) -> str:
    key = get_settings().app_secret_key.encode("utf-8")
    return hmac.new(key, payload.encode("utf-8"), hashlib.sha256).hexdigest()


def normalize_username(username: str) -> str:
    username = username.strip().lower()
    if len(username) < 3:
        raise AuthError("Логин должен быть не короче 3 символов")
    if len(username) > 64:
        raise AuthError("Логин должен быть не длиннее 64 символов")
    return username


def validate_password(password: str) -> None:
    if len(password) < 8:
        raise AuthError("Пароль должен быть не короче 8 символов")


def row_to_user(row: dict[str, Any] | None) -> CurrentUser:
    if row is None:
        raise AuthError("Пользователь не найден")
    return CurrentUser(id=str(row["id"]), username=row["username"])
