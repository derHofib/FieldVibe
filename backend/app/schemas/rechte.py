from pydantic import BaseModel


class RechteBereichRead(BaseModel):
    key: str
    label: str
    aktionen: list[str]
    scopes: list[str]
    modul: str | None


class RechteRegistryRead(BaseModel):
    bereiche: list[RechteBereichRead]
    scopes: list[str]
