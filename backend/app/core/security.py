from datetime import datetime, timedelta, timezone
from enum import StrEnum
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.core.config import get_settings

_settings = get_settings()
_hasher = PasswordHasher()


class TokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"
    IMPERSONATION = "impersonation"
    KUNDENPORTAL_ACCESS = "kundenportal_access"
    KUNDENPORTAL_REFRESH = "kundenportal_refresh"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


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
