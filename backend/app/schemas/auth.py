from uuid import UUID

from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


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


class ImpersonateResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    mandant_id: UUID
    expires_in_minutes: int
