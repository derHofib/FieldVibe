from typing import Annotated
from uuid import UUID

from pydantic import AfterValidator, BaseModel, EmailStr, field_validator

from app.schemas.user import MIN_PASSWORT_LAENGE, BottomNavUpdate, OfficeNavUpdate


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
    # None bei Mitarbeiter-Antworten fuer Cookie-Clients (HttpOnly-Cookie statt
    # Body, siehe app/core/refresh_cookie.py); Portal/Partner liefern es weiter.
    refresh_token: str | None = None
    token_type: str = "bearer"


class LoginResponse(BaseModel):
    """Entweder fertiges Token-Paar oder, bei aktiver MFA, nur der kurzlebige
    Zwischen-Token fuer POST /api/auth/mfa/verifizieren."""

    access_token: str | None = None
    refresh_token: str | None = None
    token_type: str = "bearer"
    mfa_erforderlich: bool = False
    mfa_token: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str


class UserRefreshRequest(BaseModel):
    """Mitarbeiter-Refresh: ohne Token im Body kommt es aus dem Cookie."""

    refresh_token: str | None = None


class RegistrierenRequest(BaseModel):
    """Schliesst eine Einladung ab -- wiederverwendet fuer Mitarbeiter-,
    Kundenportal- und Partnerportal-Registrierung (siehe
    app/services/einladung_service.py), da die Form ueberall identisch
    ist: welcher Account daraus entsteht, entscheidet allein die Art der
    Einladung hinter dem Token, nicht der Aufrufer."""

    token: str
    name: str
    password: str


def _mindestlaenge(v: str) -> str:
    if len(v) < MIN_PASSWORT_LAENGE:
        raise ValueError(f"Passwort muss mindestens {MIN_PASSWORT_LAENGE} Zeichen haben")
    return v


# Nur fuer die Passwort-vergessen/-aendern-Endpunkte: registrieren (8 Zeichen)
# und die Admin-Funktion "Passwort direkt setzen" behalten ihre bisherige Regel.
NeuesPasswort = Annotated[str, AfterValidator(_mindestlaenge)]


class PasswortVergessenRequest(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class PasswortZuruecksetzenRequest(BaseModel):
    token: str
    new_password: NeuesPasswort


class PasswortAendernRequest(BaseModel):
    old_password: str
    new_password: NeuesPasswort


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
    # Gespiegelt aus AccountTyp.darf_zeiten_buchen (siehe
    # app/services/rechte_service.py:darf_zeiten_buchen) -- steuert im
    # Frontend die gesamte Buchungs-Oberflaeche (Auswahl/Aktionsleiste im
    # Zeit-Tab, Seite "Zeiten buchen", fremden Timer beenden).
    darf_zeiten_buchen: bool = False
    # Gespiegelt aus AccountTyp.darf_abwesenheiten_verwalten (siehe
    # app/services/rechte_service.py) -- Soll-Zeit/Feiertage pflegen,
    # fremdes Soll/Saldo lesen.
    darf_abwesenheiten_verwalten: bool = False
    name: str
    email: str
    impersonated_by: UUID | None = None
    mfa_aktiv: bool = False
    # Mandant verlangt MFA (firmendaten.mfa_pflicht) -- dann ist Deaktivieren gesperrt.
    mfa_pflicht: bool = False
    # Pflicht ist an, der Account hat noch keine MFA: das Token erlaubt nur den
    # Einrichtungsweg, das Frontend zeigt die Einrichtung statt der App.
    mfa_einrichtung_erforderlich: bool = False
    deaktivierte_module: list[str] = []
    # Individualisierte Bottom-Nav (siehe app/models/user.py) -- None =
    # Frontend faellt auf die Standardauswahl zurueck.
    bottom_nav_items: BottomNavUpdate | None = None
    # Individualisierte Office-Seitenleiste (siehe app/models/user.py) --
    # None = Frontend zeigt alle sichtbaren Seiten (bisheriges Verhalten).
    office_nav_items: OfficeNavUpdate | None = None
    # Effektive Rechte-Matrix dieser Session (Bereich -> Liste erlaubter
    # Aktionen). role != "custom" (mandant_admin/super_admin/loesch_*)
    # bekommt IMMER alle Bereiche/Aktionen, da diese Rollen ohnehin an
    # jedem require_recht()-Gate vorbeikommen (siehe app/api/deps.py) --
    # das Frontend kann so unconditionell auf dieser Matrix pruefen, statt
    # Rollennamen fest zu verdrahten.
    rechte: dict[str, list[str]] = {}
    # Reichweite je Recht (Bereich -> Aktion -> Scope, siehe
    # app/core/rechte_registry.py); nur vorhandene Rechte, role != "custom"
    # bekommt "mandant". Noch ohne UI-Auswertung.
    rechte_scopes: dict[str, dict[str, str]] = {}


class ImpersonateResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    mandant_id: UUID
    expires_in_minutes: int
