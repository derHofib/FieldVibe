from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class AuditEintragRead(BaseModel):
    id: int
    zeit: datetime
    akteur_typ: str
    actor_user_id: UUID | None
    actor_name: str | None
    aktion: str
    entity_type: str | None
    entity_id: UUID | None
    payload: dict
    request_id: str | None
    ip: str | None


class AuditListe(BaseModel):
    eintraege: list[AuditEintragRead]
    gesamt: int


class AuditKettenFehler(BaseModel):
    seq: int | None
    audit_log_id: int | None
    grund: str


class AuditVerifikation(BaseModel):
    ok: bool
    geprueft: int
    kopf_seq: int | None
    kopf_hash: str | None
    ohne_siegel: int
    legacy_eintraege: int
    fehler: list[AuditKettenFehler]
