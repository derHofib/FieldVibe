from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.formular import (
    Formular,
    FormularAuftragstypZuordnung,
    Formularfeld,
    VorgangFormular,
)
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


async def felder_fuer(session: AsyncSession, formular_id: UUID) -> list[Formularfeld]:
    result = await session.execute(
        select(Formularfeld)
        .where(Formularfeld.formular_id == formular_id)
        .order_by(Formularfeld.reihenfolge)
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
    """Friert Name und Felddefinitionen zum Startzeitpunkt einer Ausfuellung
    ein (siehe VorgangFormular.formular_snapshot) -- spaetere Aenderungen an
    der Formular-Vorlage duerfen diese Ausfuellung nicht mehr beeinflussen."""
    return {
        "name": formular.name,
        "felder": [
            {
                "id": str(f.id),
                "feld_typ": f.feld_typ,
                "label": f.label,
                "hilfetext": f.hilfetext,
                "pflichtfeld": f.pflichtfeld,
                "reihenfolge": f.reihenfolge,
                "optionen": f.optionen,
            }
            for f in felder
        ],
    }


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
