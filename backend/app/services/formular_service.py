from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.anlage import Anlage
from app.models.formular import (
    Formular,
    FormularAuftragstypZuordnung,
    Formularfeld,
    VorgangFormular,
)
from app.models.kunde import Kunde
from app.models.standort import Standort
from app.models.vorgang import Vorgang
from app.schemas.formular import (
    FormularAuftragstypZuordnungRead,
    FormularfeldRead,
    FormularRead,
    FormularVerfuegbar,
    VorgangFormularRead,
)
from app.services import storage_service

FELDTYPEN_MIT_DATEI = ("foto", "unterschrift")

# Deutsche Labels fuer Leistungstyp-Werte beim Auto-Fill (siehe
# auto_fill_werte) -- Frontend-Pendant ist LEISTUNGSTYP_LABEL in
# frontend/src/utils/formular.ts, hier bewusst dupliziert statt geteilt, da
# Backend und Frontend keine gemeinsame Konstanten-Quelle haben.
LEISTUNGSTYP_LABEL = {
    "installation": "Installation",
    "pruefung": "Prüfung",
    "wartung": "Wartung",
    "stoerung": "Störung",
    "beratung": "Beratung",
    "planung": "Planung",
}


async def felder_fuer(session: AsyncSession, formular_id: UUID) -> list[Formularfeld]:
    result = await session.execute(
        select(Formularfeld)
        .where(Formularfeld.formular_id == formular_id)
        .order_by(Formularfeld.seite, Formularfeld.y_mm, Formularfeld.x_mm)
    )
    return list(result.scalars().all())


async def zuordnungen_fuer(session: AsyncSession, formular_id: UUID) -> list[FormularAuftragstypZuordnung]:
    result = await session.execute(
        select(FormularAuftragstypZuordnung).where(
            FormularAuftragstypZuordnung.formular_id == formular_id
        )
    )
    return list(result.scalars().all())


async def to_read_model(session: AsyncSession, formular: Formular) -> FormularRead:
    felder = await felder_fuer(session, formular.id)
    zuordnungen = await zuordnungen_fuer(session, formular.id)
    return FormularRead(
        **{k: getattr(formular, k) for k in FormularRead.model_fields if k not in ("felder", "zuordnungen")},
        felder=[FormularfeldRead.model_validate(f) for f in felder],
        zuordnungen=[FormularAuftragstypZuordnungRead.model_validate(z) for z in zuordnungen],
    )


def snapshot_von(formular: Formular, felder: list[Formularfeld]) -> dict:
    """Friert Name, Seitenlayout und Felddefinitionen zum Startzeitpunkt
    einer Ausfuellung ein (siehe VorgangFormular.formular_snapshot) --
    spaetere Aenderungen an der Formular-Vorlage duerfen diese Ausfuellung
    nicht mehr beeinflussen. snapshot_version unterscheidet die freie
    Positionierung (3) vom aelteren 12-Spalten-Raster (2) und den
    urspruenglichen, bereits abgeschlossenen Ausfuellungen ohne Layout-Daten
    (siehe generate_formular_pdf, das je Version auf den passenden
    Renderer verzweigt und aeltere Versionen nie neu erzeugt)."""
    return {
        "snapshot_version": 3,
        "name": formular.name,
        "anzahl_seiten": formular.anzahl_seiten,
        "felder": [
            {
                "id": str(f.id),
                "feld_typ": f.feld_typ,
                "label": f.label,
                "hilfetext": f.hilfetext,
                "pflichtfeld": f.pflichtfeld,
                "reihenfolge": f.reihenfolge,
                "optionen": f.optionen,
                "seite": f.seite,
                "x_mm": f.x_mm,
                "y_mm": f.y_mm,
                "breite_mm": f.breite_mm,
                "hoehe_mm": f.hoehe_mm,
                "datenquelle": f.datenquelle,
            }
            for f in felder
        ],
    }


def _adresse_einzeilig(adresse: dict | None) -> str | None:
    adresse = adresse or {}
    teile = []
    if adresse.get("strasse"):
        teile.append(str(adresse["strasse"]))
    ort = " ".join(str(adresse[k]) for k in ("plz", "ort") if adresse.get(k))
    if ort:
        teile.append(ort)
    return ", ".join(teile) or None


def auto_fill_werte(
    felder: list[Formularfeld],
    vorgang: Vorgang,
    kunde: Kunde | None,
    anlage: Anlage | None,
    standort: Standort | None,
    zugewiesener_name: str | None,
) -> dict[str, Any]:
    """Loest fuer jedes Feld mit gesetzter datenquelle (siehe
    FORMULARFELD_DATENQUELLEN) den passenden Wert aus dem Vorgang/Kunde/
    Anlage/Standort auf -- Ergebnis wird beim Start einer Ausfuellung als
    initiale antworten uebergeben (siehe start_vorgang_formular in
    app/api/routes/vorgang_formulare.py). Fehlt die referenzierte Entitaet
    (z.B. anlage.* an einem Vorgang ohne anlage_id), wird das Feld einfach
    ausgelassen statt einen Fehler zu werfen -- der Techniker fuellt es
    dann wie gewohnt manuell aus."""
    quellen: dict[str, Any] = {
        "vorgang.vorgangsnummer": vorgang.vorgangsnummer,
        "vorgang.titel": vorgang.titel,
        "vorgang.beschreibung": vorgang.beschreibung,
        "vorgang.leistungstyp": LEISTUNGSTYP_LABEL.get(vorgang.leistungstyp, vorgang.leistungstyp),
        "vorgang.faelligkeit_am": (
            vorgang.faelligkeit_am.date().isoformat() if vorgang.faelligkeit_am else None
        ),
        "vorgang.adresse": _adresse_einzeilig(vorgang.adresse),
        "vorgang.zugewiesener_name": zugewiesener_name,
    }
    if kunde is not None:
        quellen["kunde.kundennummer"] = kunde.kundennummer
        quellen["kunde.name"] = kunde.name
        quellen["kunde.adresse"] = _adresse_einzeilig(kunde.adresse)
        erster_ansprechpartner = kunde.ansprechpartner[0] if kunde.ansprechpartner else None
        quellen["kunde.ansprechpartner"] = (
            erster_ansprechpartner.get("name") if erster_ansprechpartner else None
        )
    if anlage is not None:
        quellen["anlage.bezeichnung"] = anlage.bezeichnung
        quellen["anlage.adresse"] = _adresse_einzeilig(anlage.adresse)
        quellen["anlage.hersteller"] = anlage.hersteller
        quellen["anlage.modell"] = anlage.modell
        quellen["anlage.seriennummer"] = anlage.seriennummer
        quellen["anlage.anlagentyp"] = anlage.anlagentyp
    if standort is not None:
        quellen["standort.bezeichnung"] = standort.bezeichnung
        quellen["standort.adresse"] = _adresse_einzeilig(standort.adresse)

    antworten: dict[str, Any] = {}
    for feld in felder:
        if feld.datenquelle is None:
            continue
        wert = quellen.get(feld.datenquelle)
        if wert is not None:
            antworten[str(feld.id)] = wert
    return antworten


async def verfuegbare_formulare_fuer(
    session: AsyncSession, vorgang: Vorgang
) -> list[FormularVerfuegbar]:
    result = await session.execute(
        select(Formular, FormularAuftragstypZuordnung.pflicht_vor_abschluss)
        .join(FormularAuftragstypZuordnung, FormularAuftragstypZuordnung.formular_id == Formular.id)
        .where(
            FormularAuftragstypZuordnung.leistungstyp == vorgang.leistungstyp,
            Formular.aktiv.is_(True),
        )
        .order_by(Formular.name)
    )
    return [
        FormularVerfuegbar(
            id=formular.id,
            name=formular.name,
            beschreibung=formular.beschreibung,
            pflicht_vor_abschluss=pflicht,
        )
        for formular, pflicht in result.all()
    ]


async def offene_pflichtformulare(session: AsyncSession, vorgang: Vorgang) -> list[str]:
    """Namen der fuer den Leistungstyp dieses Vorgangs als 'pflicht vor
    Abschluss' markierten Formulare, die noch nicht mindestens einmal
    abgeschlossen wurden -- blockiert das Schliessen des Vorgangs (siehe
    PATCH /api/vorgaenge/{id} in app/api/routes/vorgaenge.py)."""
    pflicht_formulare = (
        await session.execute(
            select(Formular)
            .join(FormularAuftragstypZuordnung, FormularAuftragstypZuordnung.formular_id == Formular.id)
            .where(
                FormularAuftragstypZuordnung.leistungstyp == vorgang.leistungstyp,
                FormularAuftragstypZuordnung.pflicht_vor_abschluss.is_(True),
                Formular.aktiv.is_(True),
            )
        )
    ).scalars().all()
    if not pflicht_formulare:
        return []

    erledigt_ids = set(
        (
            await session.execute(
                select(VorgangFormular.formular_id).where(
                    VorgangFormular.vorgang_id == vorgang.id,
                    VorgangFormular.status == "abgeschlossen",
                    VorgangFormular.formular_id.in_([f.id for f in pflicht_formulare]),
                )
            )
        ).scalars().all()
    )
    return [f.name for f in pflicht_formulare if f.id not in erledigt_ids]


def to_vorgang_formular_read(vorgang_formular: VorgangFormular) -> VorgangFormularRead:
    """Loest gespeicherte Foto-/Unterschrift-Antworten (siehe FELDTYPEN_MIT_DATEI)
    zu abrufbaren presigned URLs auf, ohne dabei die auf der ORM-Instanz
    gehaltene antworten-JSONB in place zu veraendern (sonst haelt SQLAlchemy
    das faelschlich fuer eine zu speichernde Aenderung)."""
    data = VorgangFormularRead.model_validate(vorgang_formular)
    felder_by_id = {f["id"]: f for f in vorgang_formular.formular_snapshot.get("felder", [])}
    aufgeloeste_antworten = dict(vorgang_formular.antworten)
    for feld_id, antwort in vorgang_formular.antworten.items():
        feld = felder_by_id.get(feld_id)
        if (
            feld is not None
            and feld["feld_typ"] in FELDTYPEN_MIT_DATEI
            and isinstance(antwort, dict)
            and antwort.get("key")
        ):
            aufgeloeste_antworten[feld_id] = {**antwort, "url": storage_service.presigned_get_url(antwort["key"])}
    data.antworten = aufgeloeste_antworten
    return data
