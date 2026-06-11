import base64
import hashlib
import json
from typing import Any

from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes

from api.db import get_connection
from api.settings import get_settings


class CredentialsError(ValueError):
    pass


def save_service_credentials(
    user_id: str,
    service: str,
    auth_type: str,
    data: dict[str, Any],
    label: str = "default",
) -> None:
    encrypted_data = encrypt_credentials(data)
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO service_credentials (
                user_id,
                service,
                auth_type,
                label,
                data_encrypted
            )
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id, service, label)
            DO UPDATE SET
                auth_type = EXCLUDED.auth_type,
                data_encrypted = EXCLUDED.data_encrypted,
                updated_at = now()
            """,
            (user_id, service, auth_type, label, encrypted_data),
        )


def get_service_credentials(
    user_id: str,
    service: str,
    label: str = "default",
) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT data_encrypted
            FROM service_credentials
            WHERE user_id = %s AND service = %s AND label = %s
            """,
            (user_id, service, label),
        ).fetchone()

    if row is None:
        return None
    return decrypt_credentials(row["data_encrypted"])


def has_service_credentials(user_id: str, service: str, label: str = "default") -> bool:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT 1
            FROM service_credentials
            WHERE user_id = %s AND service = %s AND label = %s
            """,
            (user_id, service, label),
        ).fetchone()

    return row is not None


def encrypt_credentials(data: dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    nonce = get_random_bytes(12)
    cipher = AES.new(get_encryption_key(), AES.MODE_GCM, nonce=nonce)
    ciphertext, tag = cipher.encrypt_and_digest(payload)
    return base64.urlsafe_b64encode(nonce + tag + ciphertext).decode("ascii")


def decrypt_credentials(encrypted_data: str) -> dict[str, Any]:
    try:
        raw = base64.urlsafe_b64decode(encrypted_data.encode("ascii"))
        nonce = raw[:12]
        tag = raw[12:28]
        ciphertext = raw[28:]
        cipher = AES.new(get_encryption_key(), AES.MODE_GCM, nonce=nonce)
        payload = cipher.decrypt_and_verify(ciphertext, tag)
        data = json.loads(payload.decode("utf-8"))
    except Exception as error:
        raise CredentialsError("Cannot decrypt service credentials") from error

    if not isinstance(data, dict):
        raise CredentialsError("Invalid service credentials payload")
    return data


def get_encryption_key() -> bytes:
    return hashlib.sha256(get_settings().app_secret_key.encode("utf-8")).digest()
