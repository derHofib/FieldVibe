from pydantic import BaseModel, field_validator


def _getrimmt(v):
    if isinstance(v, str):
        v = v.strip()
        return v or None
    return v


class Leistungsort(BaseModel):
    """Snapshot auf Rechnung/Angebot. Der Mietername gehoert bewusst nicht automatisch hierher: die
    Bezeichnung (z. B. Einheit) tippt das Buero im Entwurf selbst."""

    bezeichnung: str | None = None
    strasse: str | None = None
    plz: str | None = None
    ort: str | None = None
    land: str | None = None

    _trimmen = field_validator("bezeichnung", "strasse", "plz", "ort", "land", mode="before")(_getrimmt)


def kunden_referenz_bereinigen(wert: str | None) -> str | None:
    """Leer/whitespace = nicht gesetzt (Leeren ist erlaubt)."""
    return (wert or "").strip()[:200] or None
