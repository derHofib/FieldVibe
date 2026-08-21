from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class AnsprechpartnerEintrag(BaseModel):
    """Ein einzelner Ansprechpartner innerhalb einer JSONB-Liste -- gemeinsam
    genutzt von Kunde (siehe app/schemas/kunde.py) und Partner (siehe
    app/schemas/partner.py), da beide dieselbe Kategorisierung brauchen."""

    id: UUID = Field(default_factory=uuid4)
    name: str
    position: str | None = None
    telefon: str | None = None
    email: str | None = None
    # Tagesgeschaeft (Terminabsprachen etc.) vs. reiner Eskalationskontakt --
    # ein Ansprechpartner kann beides, eines von beiden oder keines sein.
    operativ: bool = False
    # 1 = Erstkontakt, 2 = Eskalation, 3 = Geschaeftsleitung/Notfall; None =
    # nicht Teil der Eskalationskette.
    eskalationsstufe: int | None = Field(default=None, ge=1, le=3)
    notiz: str | None = None
