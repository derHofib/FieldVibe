from uuid import UUID

from pydantic import BaseModel, EmailStr, field_validator


class LoginRequest(BaseModel):
    email: EmailStr
    password: str

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, v: str) -> str:
        # Muss exakt spiegeln, wie E-Mails bei der Anlage normalisiert werden
        # (siehe app/schemas/user.py, app/schemas/kundenportal.py) -- sonst
        # wuerde Groß-/Kleinschreibung beim Login wieder eine Rolle spielen.
        return v.strip().lower()


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class CurrentUser(BaseModel):
    id: UUID
    mandant_id: UUID | None
    mandant_name: str | None = None
    role: str
    name: str
    email: str
    impersonated_by: UUID | None = None
    deaktivierte_module: list[str] = []


class ImpersonateResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    mandant_id: UUID
    expires_in_minutes: int
