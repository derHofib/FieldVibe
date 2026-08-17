from uuid import UUID

from pydantic import BaseModel, EmailStr, field_validator

from app.schemas.user import BottomNavUpdate


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


class RegistrierenRequest(BaseModel):
    """Schliesst eine Einladung ab -- wiederverwendet fuer Mitarbeiter-,
    Kundenportal- und Partnerportal-Registrierung (siehe
    app/services/einladung_service.py), da die Form ueberall identisch
    ist: welcher Account daraus entsteht, entscheidet allein die Art der
    Einladung hinter dem Token, nicht der Aufrufer."""

    token: str
    name: str
    password: str


class CurrentUser(BaseModel):
    id: UUID
    mandant_id: UUID | None
    mandant_name: str | None = None
    role: str
    account_typ_id: UUID | None = None
    account_typ_name: str | None = None
    # Gespiegelt aus AccountTyp.nur_zugewiesene_kunden -- ersetzt im
    # Frontend das fruehere role === "techniker" fuer rein UX-seitige
    # Unterscheidungen (z.B. "eigenes Fahrzeug"-Materialbestand vorschlagen).
    nur_zugewiesene_kunden: bool = False
    # Gespiegelt aus darf_vorgang_selbst_uebernehmen (siehe
    # app/services/rechte_service.py) -- steuert, ob das Frontend den
    # "Ticket übernehmen"-Button auf der Vorgang-Detailseite anzeigt.
    darf_vorgaenge_selbst_uebernehmen: bool = False
    name: str
    email: str
    impersonated_by: UUID | None = None
    deaktivierte_module: list[str] = []
    # Individualisierte Bottom-Nav (siehe app/models/user.py) -- None =
    # Frontend faellt auf die Standardauswahl zurueck.
    bottom_nav_items: BottomNavUpdate | None = None
    # Effektive Rechte-Matrix dieser Session (Bereich -> Liste erlaubter
    # Aktionen). role != "custom" (mandant_admin/super_admin/loesch_*)
    # bekommt IMMER alle Bereiche/Aktionen, da diese Rollen ohnehin an
    # jedem require_recht()-Gate vorbeikommen (siehe app/api/deps.py) --
    # das Frontend kann so unconditionell auf dieser Matrix pruefen, statt
    # Rollennamen fest zu verdrahten.
    rechte: dict[str, list[str]] = {}


class ImpersonateResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    mandant_id: UUID
    expires_in_minutes: int
