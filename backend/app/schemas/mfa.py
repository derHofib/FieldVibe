from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.auth import TokenPair

# Obergrenze schuetzt vor absurd langen Eingaben; gueltige Werte sind 6 Ziffern
# bzw. ein Wiederherstellungscode (19 Zeichen mit Trennstrichen).
_CodeFeld = Field(min_length=1, max_length=40)


class MfaStatus(BaseModel):
    aktiv: bool
    pflicht: bool
    einrichtung_erforderlich: bool
    wiederherstellungscodes_uebrig: int
    aktiviert_am: datetime | None = None


class MfaEinrichtung(BaseModel):
    secret: str
    otpauth_uri: str
    qr_svg_data_uri: str


class MfaCodeRequest(BaseModel):
    code: str = _CodeFeld


class MfaPasswortCodeRequest(BaseModel):
    password: str
    code: str = _CodeFeld


class MfaAktiviert(TokenPair):
    """Frisches Token-Paar (die Aktivierung widerruft alle bisherigen Tokens)
    plus die einmalig sichtbaren Wiederherstellungscodes."""

    wiederherstellungscodes: list[str]


class MfaWiederherstellungscodes(BaseModel):
    wiederherstellungscodes: list[str]


class MfaVerifizierenRequest(BaseModel):
    mfa_token: str
    code: str = _CodeFeld
