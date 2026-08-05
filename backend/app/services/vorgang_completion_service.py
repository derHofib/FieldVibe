from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dauerauftrag import Dauerauftrag
from app.models.dauerauftrag_ziel import DauerauftragZiel
from app.models.mangel import Mangel
from app.models.material_bedarf import MaterialBedarf
from app.models.pruefzyklus import Pruefzyklus
from app.models.vorgang import Vorgang
from app.models.vorgang_anlage import VorgangAnlage
from app.models.vorgang_event import VorgangEvent
from app.services.date_utils import add_intervall
from app.services.numbering_service import next_vorgangsnummer

# Ab hier gilt ein Vorgang als final -- weder ueber PATCH /vorgaenge/{id} noch
# ueber neue Events (Kommentar/Foto/Unterschrift) veraenderbar. "abgerechnet"
# wird ausschliesslich intern von rechnungen.py gesetzt (nicht ueber diese
# Endpunkte), bleibt also von dieser Sperre unberuehrt erreichbar.
VORGANG_STATUS_GESCHLOSSEN = frozenset({"abgeschlossen", "abgerechnet", "storniert"})


async def close_vorgang(
    session: AsyncSession,
    vorgang: Vorgang,
    *,
    alter_status: str,
    author_user_id: UUID,
    folge_leistungstyp: str | None = None,
) -> Vorgang | None:
    """Schliesst einen Vorgang ab: setzt Status/abgeschlossen_am, protokolliert
    den Statuswechsel und stoesst alle Folgeaktionen an (Pruefzyklus- und
    Dauerauftrag-Faelligkeit fortschreiben, verknuepfte Maengel als behoben
    markieren). Gemeinsam genutzt von PATCH /vorgaenge/{id} (status=abgeschlossen)
    und dem Unterschrift-Upload, der einen Vorgang automatisch abschliesst.

    folge_leistungstyp ist ausschliesslich fuer den Beratung-Workflow
    gedacht (siehe app/api/routes/vorgaenge.py fuer die Validierung, dass
    dies nur bei leistungstyp="beratung" mitgeschickt werden darf): legt
    einen Folge-Vorgang mit diesem Leistungstyp an, uebernimmt Kunde/
    Anlage(n)/Standort/Vertrag sowie die offenen Angebots-Materialbedarfe
    (die am Original-Vorgang zur Dokumentation stehen bleiben, aber auf
    Status "uebertragen" wechseln, damit sie nicht doppelt als offen
    gelten) und gibt den neuen Vorgang zurueck, damit der Aufrufer ihn in
    der Antwort verlinken kann."""
    vorgang.status = "abgeschlossen"
    if vorgang.abgeschlossen_am is None:
        vorgang.abgeschlossen_am = datetime.now(timezone.utc)

    session.add(
        VorgangEvent(
            mandant_id=vorgang.mandant_id,
            vorgang_id=vorgang.id,
            event_type="status_change",
            author_user_id=author_user_id,
            payload={"von": alter_status, "nach": "abgeschlossen"},
        )
    )

    # Schliesst dieser Vorgang einen vom Pruefzyklen-Scheduler angelegten
    # Auftrag ab, gilt die Pruefung als durchgefuehrt: Faelligkeit
    # fortschreiben, offener_vorgang_id leeren -- sonst wuerde der naechste
    # Scheduler-Lauf sofort einen neuen Vorgang fuer denselben (jetzt
    # erledigten) Zyklus anlegen.
    zyklus = (
        await session.execute(
            select(Pruefzyklus).where(Pruefzyklus.offener_vorgang_id == vorgang.id)
        )
    ).scalar_one_or_none()
    if zyklus is not None:
        zyklus.letzte_pruefung_am = vorgang.abgeschlossen_am
        zyklus.naechste_pruefung_am = add_intervall(
            zyklus.letzte_pruefung_am, zyklus.intervall_einheit, zyklus.intervall_wert
        )
        zyklus.offener_vorgang_id = None

    # Schliesst dieser Vorgang das Ziel eines Dauerauftrags ab (wiederkehrender
    # Auftrag, siehe app/models/dauerauftrag.py, gebuendelt ueber
    # app/models/dauerauftrag_ziel.py): naechste Faelligkeit dieses Ziels
    # fortschreiben und offener_vorgang_id leeren, damit der naechste
    # Scheduler-Lauf ueberhaupt erst einen Folge-Vorgang fuer GENAU DIESES
    # Ziel anlegen darf -- andere Ziele desselben Buendels sind davon
    # unabhaengig und laufen unbeeinflusst weiter.
    dauerauftrag_ziel = (
        await session.execute(
            select(DauerauftragZiel).where(DauerauftragZiel.offener_vorgang_id == vorgang.id)
        )
    ).scalar_one_or_none()
    dauerauftrag = (
        await session.get(Dauerauftrag, dauerauftrag_ziel.dauerauftrag_id)
        if dauerauftrag_ziel is not None
        else None
    )
    if dauerauftrag_ziel is not None and dauerauftrag is not None:
        geplante_faelligkeit = dauerauftrag_ziel.naechste_faelligkeit_am
        abgeschlossen_datum = vorgang.abgeschlossen_am.date()
        tage_abweichung = (abgeschlossen_datum - geplante_faelligkeit).days

        if (
            dauerauftrag.toleranz_frueh_tage is not None
            and tage_abweichung < -dauerauftrag.toleranz_frueh_tage
        ):
            session.add(
                VorgangEvent(
                    mandant_id=vorgang.mandant_id,
                    vorgang_id=vorgang.id,
                    event_type="system",
                    is_system=True,
                    body=(
                        f"Hinweis: {-tage_abweichung} Tage vor der geplanten "
                        f"Fälligkeit ({geplante_faelligkeit.isoformat()}) abgeschlossen."
                    ),
                )
            )
        elif (
            dauerauftrag.toleranz_spaet_tage is not None
            and tage_abweichung > dauerauftrag.toleranz_spaet_tage
        ):
            session.add(
                VorgangEvent(
                    mandant_id=vorgang.mandant_id,
                    vorgang_id=vorgang.id,
                    event_type="system",
                    is_system=True,
                    body=(
                        f"Hinweis: {tage_abweichung} Tage nach der geplanten "
                        f"Fälligkeit ({geplante_faelligkeit.isoformat()}) abgeschlossen."
                    ),
                )
            )

        # "rollierend" (Default): Frist wandert mit dem tatsaechlichen
        # Abschlussdatum, damit liegen gebliebene Auftraege sich nicht selbst
        # einholen. "fest": Frist bleibt an einem festen Kalenderrhythmus
        # verankert, unabhaengig davon, wann tatsaechlich abgeschlossen wurde.
        basis = (
            abgeschlossen_datum if dauerauftrag.modus == "rollierend" else geplante_faelligkeit
        )
        dauerauftrag_ziel.naechste_faelligkeit_am = basis + timedelta(
            days=dauerauftrag.intervall_tage
        )
        dauerauftrag_ziel.offener_vorgang_id = None

    # Schliesst dieser Vorgang eine aus einem angenommenen Angebot entstandene
    # Reparatur ab, gelten die zugehoerigen Maengel als behoben (siehe
    # app/api/routes/angebote.py: dort wird reparatur_vorgang_id beim
    # Annehmen des Angebots gesetzt).
    offene_maengel = (
        await session.execute(
            select(Mangel).where(
                Mangel.reparatur_vorgang_id == vorgang.id, Mangel.status != "behoben"
            )
        )
    ).scalars().all()
    for mangel in offene_maengel:
        mangel.status = "behoben"
        mangel.behoben_am = vorgang.abgeschlossen_am

    if folge_leistungstyp is None:
        return None

    vorgangsnummer = await next_vorgangsnummer(session, vorgang.mandant_id)
    folge_vorgang = Vorgang(
        mandant_id=vorgang.mandant_id,
        vorgangsnummer=vorgangsnummer,
        kunde_id=vorgang.kunde_id,
        anlage_id=vorgang.anlage_id,
        standort_id=vorgang.standort_id,
        vertrag_id=vorgang.vertrag_id,
        parent_vorgang_id=vorgang.id,
        titel=vorgang.titel,
        beschreibung=vorgang.beschreibung,
        abrechnungsart=vorgang.abrechnungsart,
        leistungstyp=folge_leistungstyp,
        prioritaet=vorgang.prioritaet,
        erstellt_von=author_user_id,
    )
    session.add(folge_vorgang)
    await session.flush()

    weitere_anlagen = (
        await session.execute(
            select(VorgangAnlage.anlage_id).where(VorgangAnlage.vorgang_id == vorgang.id)
        )
    ).scalars().all()
    for anlage_id in weitere_anlagen:
        session.add(
            VorgangAnlage(vorgang_id=folge_vorgang.id, anlage_id=anlage_id, mandant_id=vorgang.mandant_id)
        )

    offene_angebots_bedarfe = (
        await session.execute(
            select(MaterialBedarf).where(
                MaterialBedarf.vorgang_id == vorgang.id,
                MaterialBedarf.zweck == "angebot",
                MaterialBedarf.status == "offen",
            )
        )
    ).scalars().all()
    for bedarf in offene_angebots_bedarfe:
        session.add(
            MaterialBedarf(
                mandant_id=vorgang.mandant_id,
                material_id=bedarf.material_id,
                vorgang_id=folge_vorgang.id,
                menge=bedarf.menge,
                notiz=bedarf.notiz,
                zweck=bedarf.zweck,
                erstellt_von=author_user_id,
                uebernommen_von_id=bedarf.id,
            )
        )
        bedarf.status = "uebertragen"

    session.add(
        VorgangEvent(
            mandant_id=vorgang.mandant_id,
            vorgang_id=vorgang.id,
            event_type="system",
            is_system=True,
            author_user_id=author_user_id,
            body=f"Folge-Vorgang {vorgangsnummer} ({folge_leistungstyp}) angelegt.",
            payload={"folge_vorgang_id": str(folge_vorgang.id)},
        )
    )
    session.add(
        VorgangEvent(
            mandant_id=vorgang.mandant_id,
            vorgang_id=folge_vorgang.id,
            event_type="system",
            is_system=True,
            author_user_id=author_user_id,
            body=f"Angelegt als Folge-Vorgang von {vorgang.vorgangsnummer}.",
            payload={"quelle_vorgang_id": str(vorgang.id)},
        )
    )

    return folge_vorgang
