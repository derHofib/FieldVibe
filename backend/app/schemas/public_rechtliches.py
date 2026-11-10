from urllib.parse import urlsplit

from pydantic import BaseModel

_URL_MAX_LAENGE = 2048


def ist_http_url(wert: object) -> bool:
    """Nur http/https mit Host -- schliesst javascript:-/data:-URLs aus, die
    als href auf der Login-Seite ein XSS-Vektor waeren."""
    if not isinstance(wert, str) or not wert or len(wert) > _URL_MAX_LAENGE:
        return False
    if any(c.isspace() or ord(c) < 32 for c in wert):
        return False
    try:
        teile = urlsplit(wert)
    except ValueError:
        return False
    return teile.scheme.lower() in ("http", "https") and bool(teile.netloc)


class RechtlichesAnbieter(BaseModel):
    """Bewusst nur die Angaben, die ohnehin ins Impressum bzw. die
    Verantwortlichen-Angabe gehoeren -- keine Bankdaten, keine
    Steuernummer."""

    name: str
    strasse: str | None = None
    plz: str | None = None
    ort: str | None = None
    land: str | None = None
    telefon: str | None = None
    email: str | None = None
    website: str | None = None
    geschaeftsfuehrung: str | None = None
    handelsregister: str | None = None
    ust_idnr: str | None = None


class RechtlichesRead(BaseModel):
    impressum_url: str | None = None
    datenschutz_url: str | None = None
    # Barrierefreiheitserklaerung (BFSG): externe URL des Betriebs hat Vorrang
    # vor der Platzhalter-Seite /barrierefreiheit, die Kontakt und Stand zeigt.
    barrierefreiheit_url: str | None = None
    barrierefreiheit_kontakt_email: str | None = None
    barrierefreiheit_stand: str | None = None
    anbieter: RechtlichesAnbieter | None = None
