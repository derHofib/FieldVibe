from datetime import datetime

from pydantic import BaseModel

from app.schemas.angebot import AngebotRead
from app.schemas.anlage import AnlageRead
from app.schemas.email import EmailLogRead
from app.schemas.kunde import KundeRead
from app.schemas.kundenportal import KundenportalZugangRead
from app.schemas.rechnung import RechnungRead
from app.schemas.standort import StandortRead
from app.schemas.vertrag import VertragRead
from app.schemas.vorgang import VorgangRead
from app.schemas.vorgang_event import VorgangEventRead


class VorgangMitEreignissen(VorgangRead):
    ereignisse: list[VorgangEventRead]


class KundeDatenexport(BaseModel):
    """Alle personenbezogenen Daten zu einem Kunden in einer maschinenlesbaren
    Struktur -- fuer Auskunftsersuchen (Art. 15 DSGVO) und Datenuebertragbarkeit
    (Art. 20 DSGVO). Enthaelt bewusst NICHT: Passwort-Hashes
    (Kundenportal-Zugaenge stehen ohne password_hash drin), archivierte
    PDF-/Foto-Binaerdaten (die Belege/Fotos selbst bleiben ueber die App
    abrufbar, hier nur Metadaten) und Daten anderer Kunden/Mandanten.
    """

    exportiert_am: datetime
    kunde: KundeRead
    standorte: list[StandortRead]
    anlagen: list[AnlageRead]
    vertraege: list[VertragRead]
    vorgaenge: list[VorgangMitEreignissen]
    angebote: list[AngebotRead]
    rechnungen: list[RechnungRead]
    emails: list[EmailLogRead]
    kundenportal_zugaenge: list[KundenportalZugangRead]
    tags: list[str]
