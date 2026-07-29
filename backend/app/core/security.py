import base64
import hashlib
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

_settings = get_settings()
_hasher = PasswordHasher()


class TokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"
    IMPERSONATION = "impersonation"
    KUNDENPORTAL_ACCESS = "kundenportal_access"
    KUNDENPORTAL_REFRESH = "kundenportal_refresh"
    KUNDENPORTAL_PASSWORD_RESET = "kundenportal_password_reset"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


# --- Mandant-Integrationen: Secrets app-seitig verschluesseln ------------
# Kein Ersatz fuer ein echtes Vault/KMS (kein Key-Rotation-Support, kein
# Audit-Trail auf Zugriff) -- aber deutlich besser als Klartext-Secrets in
# `mandant_integrationen.secret_ref`. integration_secret_key faellt auf
# jwt_secret zurueck, wenn nicht separat gesetzt (siehe config.py); in
# Produktion sollten beide unterschiedlich sein (Defense-in-Depth: ein
# geleakter JWT_SECRET allein entschluesselt dann keine Integrations-Secrets).
def _fernet() -> Fernet:
    key_material = (_settings.integration_secret_key or _settings.jwt_secret).encode()
    derived_key = base64.urlsafe_b64encode(hashlib.sha256(key_material).digest())
    return Fernet(derived_key)


def encrypt_secret(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("Secret kann nicht entschluesselt werden") from exc


def _create_token(
    *,
    subject: UUID,
    role: str,
    mandant_id: UUID | None,
    token_type: TokenType,
    expires_delta: timedelta,
    extra_claims: dict | None = None,
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(subject),
        "role": role,
        "mandant_id": str(mandant_id) if mandant_id else None,
        "type": token_type.value,
        "iat": now,
        "exp": now + expires_delta,
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, _settings.jwt_secret, algorithm=_settings.jwt_algorithm)


def create_access_token(
    *, subject: UUID, role: str, mandant_id: UUID | None
) -> str:
    return _create_token(
        subject=subject,
        role=role,
        mandant_id=mandant_id,
        token_type=TokenType.ACCESS,
        expires_delta=timedelta(minutes=_settings.access_token_expire_minutes),
    )


def create_refresh_token(
    *, subject: UUID, role: str, mandant_id: UUID | None
) -> str:
    return _create_token(
        subject=subject,
        role=role,
        mandant_id=mandant_id,
        token_type=TokenType.REFRESH,
        expires_delta=timedelta(minutes=_settings.refresh_token_expire_minutes),
    )


def create_impersonation_token(
    *, subject: UUID, role: str, mandant_id: UUID, impersonated_by: UUID
) -> str:
    return _create_token(
        subject=subject,
        role=role,
        mandant_id=mandant_id,
        token_type=TokenType.IMPERSONATION,
        expires_delta=timedelta(minutes=_settings.impersonation_token_expire_minutes),
        extra_claims={"impersonated_by": str(impersonated_by)},
    )


def decode_token(token: str) -> dict:
    return jwt.decode(token, _settings.jwt_secret, algorithms=[_settings.jwt_algorithm])


def create_kundenportal_password_reset_token(*, zugang_id: UUID) -> str:
    """Kurzlebiges Single-Purpose-Token fuer den 'Passwort vergessen'-Link,
    kein Zugriffstoken -- traegt bewusst weder role noch mandant_id/kunde_id,
    da es nur fuer den einen Zweck (PATCH /auth/reset-passwort) geprueft wird
    und sonst nirgends als Bearer-Token akzeptiert werden darf (siehe
    get_current_kunde/get_current_user, die beide einen anderen `type`
    erwarten)."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(zugang_id),
        "type": TokenType.KUNDENPORTAL_PASSWORD_RESET.value,
        "iat": now,
        "exp": now + timedelta(minutes=_settings.kundenportal_reset_token_expire_minutes),
    }
    return jwt.encode(payload, _settings.jwt_secret, algorithm=_settings.jwt_algorithm)


# Kundenportal-Tokens tragen absichtlich role="kunde" -- ein Wert, den keine
# echte User-Rolle je annimmt (siehe app.models.user.ROLES). Ein
# Kundenportal-Token kann dadurch nie versehentlich eine
# require_roles(...)-Pruefung der internen Staff-API erfuellen, selbst wenn
# beide Tokenarten denselben Header/dieselbe Signatur teilen.
_KUNDE_PSEUDOROLLE = "kunde"


def create_kundenportal_access_token(
    *, subject: UUID, mandant_id: UUID, kunde_id: UUID
) -> str:
    return _create_token(
        subject=subject,
        role=_KUNDE_PSEUDOROLLE,
        mandant_id=mandant_id,
        token_type=TokenType.KUNDENPORTAL_ACCESS,
        expires_delta=timedelta(minutes=_settings.access_token_expire_minutes),
        extra_claims={"kunde_id": str(kunde_id)},
    )


def create_kundenportal_refresh_token(
    *, subject: UUID, mandant_id: UUID, kunde_id: UUID
) -> str:
    return _create_token(
        subject=subject,
        role=_KUNDE_PSEUDOROLLE,
        mandant_id=mandant_id,
        token_type=TokenType.KUNDENPORTAL_REFRESH,
        expires_delta=timedelta(minutes=_settings.refresh_token_expire_minutes),
        extra_claims={"kunde_id": str(kunde_id)},
    )
