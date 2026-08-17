from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.audit_log import AuditLog
from app.models.kunde import Kunde
from app.models.mandant import Mandant
from app.models.notification import Notification
from app.models.rechnung import Rechnung
from app.models.user import User
from app.models.vorgang_event import VorgangEvent
from app.db.session import system_session
from app.services.email_service import send_email_and_log
from app.services.pdf_service import generate_mahnung_pdf
from app.services.rechnung_service import bezahlter_betrag, brutto_betrag, positionen_fuer, zahlungen_fuer
from app.services.zuweisung_service import abrechnung_verantwortliche_user_ids

MAHNWESEN_AKTION = "mahnwesen_eskalation_run"
# §288 Abs. 5 BGB: Pauschale steht nur gegenueber Nicht-Verbrauchern zu.
# Ohne dedizierte B2B/B2C-Kennzeichnung am Kunden dient Kunde.typ != "privat"
# als Naeherung (fehlender typ wird konservativ wie "privat" behandelt, um
# niemals einem Verbraucher zu Unrecht Unternehmer-Konditionen zu berechnen).
MAHNPAUSCHALE = Decimal("40.00")


def _ist_unternehmer(kunde: Kunde) -> bool:
    return kunde.typ not in (None, "privat")


def berechne_verzugszinsen(betrag_brutto: Decimal, tage_ueberfaellig: int, ist_unternehmer: bool) -> Decimal:
    """§288 BGB: Basiszinssatz + 9 Punkte gegenueber Unternehmern, + 5
    Punkte gegenueber Verbrauchern."""
    aufschlag = Decimal("9") if ist_unternehmer else Decimal("5")
    satz = Decimal(str(get_settings().basiszinssatz_prozent)) + aufschlag
    zins = betrag_brutto * satz / Decimal("100") / Decimal("365") * tage_ueberfaellig
    return zins.quantize(Decimal("0.01"))


def _empfaenger_email(kunde: Kunde) -> str | None:
    for ansprechpartner in kunde.ansprechpartner or []:
        email = ansprechpartner.get("email")
        if email:
            return email
    return None


def _ziel_mahnstufe(tage_ueberfaellig: int) -> int:
    settings = get_settings()
    if tage_ueberfaellig >= settings.mahnstufe_3_tage:
        return 3
    if tage_ueberfaellig >= settings.mahnstufe_2_tage:
        return 2
    if tage_ueberfaellig >= settings.mahnstufe_1_tage:
        return 1
    return 0


async def _admins_und_disponenten(session: AsyncSession, mandant_id) -> list[User]:
    user_ids = await abrechnung_verantwortliche_user_ids(session, mandant_id)
    if not user_ids:
        return []
    result = await session.execute(select(User).where(User.id.in_(user_ids)))
    return list(result.scalars().all())


async def run_mahnwesen_eskalation(mandant_ids: list[UUID] | None = None) -> dict:
    """Taeglicher Lauf: erhoeht die Mahnstufe ueberfaelliger, noch unbezahlter
    Rechnungen (Status 'versendet' mit faellig_am in der Vergangenheit) nach
    den in Settings konfigurierten Tagesschwellen. Eskaliert nur, wenn sich
    die Stufe tatsaechlich erhoeht -- verhindert taegliches Neu-Benachrich-
    tigen, solange die Rechnung auf derselben Stufe verharrt.

    `mandant_ids` grenzt wie bei run_pruefzyklen_scheduler auf die
    Mandanten ein, deren Scheduler-Stunde gerade erreicht ist; None
    bearbeitet weiterhin alle Mandanten."""
    heute = date.today()
    jetzt = datetime.now(timezone.utc)
    eskaliert = 0
    automatisch_versendet = 0
    mandanten_cache: dict[UUID, Mandant] = {}

    async with system_session() as session:
        # teilweise_bezahlt mahnt weiter -- eine Rechnung, die zu 90%
        # bezahlt ist, aber ueberfaellig bleibt, soll nicht aufhoeren zu
        # mahnen, nur weil sie den Status gewechselt hat.
        ueberfaellig_stmt = select(Rechnung).where(
            Rechnung.status.in_(("versendet", "teilweise_bezahlt")),
            Rechnung.faellig_am.isnot(None),
            Rechnung.faellig_am < heute,
        )
        if mandant_ids is not None:
            ueberfaellig_stmt = ueberfaellig_stmt.where(Rechnung.mandant_id.in_(mandant_ids))
        ueberfaellig = (await session.execute(ueberfaellig_stmt)).scalars().all()

        for rechnung in ueberfaellig:
            positionen = await positionen_fuer(session, rechnung.id)
            zahlungen = await zahlungen_fuer(session, rechnung.id)
            offener_betrag = brutto_betrag(rechnung, positionen) - bezahlter_betrag(zahlungen)
            if offener_betrag <= 0:
                continue

            tage_ueberfaellig = (heute - rechnung.faellig_am).days
            ziel_stufe = _ziel_mahnstufe(tage_ueberfaellig)
            if ziel_stufe <= rechnung.mahnstufe:
                continue

            rechnung.mahnstufe = ziel_stufe
            rechnung.letzte_mahnung_am = jetzt
            eskaliert += 1

            if rechnung.mandant_id not in mandanten_cache:
                mandanten_cache[rechnung.mandant_id] = await session.get(Mandant, rechnung.mandant_id)
            mandant = mandanten_cache[rechnung.mandant_id]
            # Default ist ein reiner interner Hinweis, kein automatischer
            # Versand -- der Mandant muss den Auto-Versand je Mahnstufe
            # bewusst im Firmenprofil aktivieren (siehe IntegrationenPage).
            automatisch_gesendet = bool((mandant.firmendaten or {}).get(f"mahnung_{ziel_stufe}_automatisch"))

            versand_hinweis = ""
            if automatisch_gesendet:
                kunde = await session.get(Kunde, rechnung.kunde_id)
                empfaenger = _empfaenger_email(kunde) if kunde is not None else None
                if kunde is not None and empfaenger:
                    # Gemahnt wird der noch offene Betrag, nicht der volle
                    # Bruttobetrag -- sonst wuerde eine bereits teilweise
                    # bezahlte Rechnung ueber den Restbetrag hinaus gemahnt.
                    ist_unternehmer = _ist_unternehmer(kunde)
                    verzugszinsen = berechne_verzugszinsen(offener_betrag, tage_ueberfaellig, ist_unternehmer)
                    pauschale = MAHNPAUSCHALE if ist_unternehmer else Decimal("0")
                    pdf_bytes = generate_mahnung_pdf(
                        mandant,
                        rechnung,
                        kunde,
                        ziel_stufe,
                        tage_ueberfaellig,
                        offener_betrag,
                        verzugszinsen,
                        pauschale,
                    )
                    await send_email_and_log(
                        session,
                        rechnung.mandant_id,
                        entity_type="rechnung",
                        entity_id=rechnung.id,
                        to=empfaenger,
                        subject=f"{ziel_stufe}. Mahnung: Rechnung {rechnung.rechnungsnummer}",
                        body=(
                            f"Sehr geehrte Damen und Herren,\n\n"
                            f"die Rechnung {rechnung.rechnungsnummer} ist seit {tage_ueberfaellig} Tagen "
                            f"ueberfaellig. Bitte begleichen Sie den offenen Betrag zeitnah -- Details siehe "
                            f"angehaengte Mahnung."
                        ),
                        attachment=(f"Mahnung-{rechnung.rechnungsnummer}.pdf", pdf_bytes, "application/pdf"),
                    )
                    automatisch_versendet += 1
                    versand_hinweis = " (automatisch per E-Mail versendet)"
                else:
                    versand_hinweis = " (automatischer Versand fehlgeschlagen: keine E-Mail-Adresse hinterlegt)"

            if rechnung.vorgang_id is not None:
                session.add(
                    VorgangEvent(
                        mandant_id=rechnung.mandant_id,
                        vorgang_id=rechnung.vorgang_id,
                        event_type="rechnung_status",
                        is_system=True,
                        body=(
                            f"Rechnung {rechnung.rechnungsnummer}: {ziel_stufe}. Mahnung "
                            f"({tage_ueberfaellig} Tage ueberfaellig){versand_hinweis}"
                        ),
                        payload={"rechnung_id": str(rechnung.id), "mahnstufe": ziel_stufe},
                    )
                )

            for empfaenger in await _admins_und_disponenten(session, rechnung.mandant_id):
                session.add(
                    Notification(
                        mandant_id=rechnung.mandant_id,
                        user_id=empfaenger.id,
                        typ="frist",
                        titel=f"Rechnung {rechnung.rechnungsnummer}: {ziel_stufe}. Mahnung faellig",
                        ref_entity_type="rechnung",
                        ref_entity_id=rechnung.id,
                    )
                )

        ergebnis = {"rechnungen_eskaliert": eskaliert, "automatisch_versendet": automatisch_versendet}
        session.add(
            AuditLog(
                mandant_id=None,
                actor_user_id=None,
                aktion=MAHNWESEN_AKTION,
                entity_type="scheduler",
                payload=ergebnis,
            )
        )
        await session.flush()

    return ergebnis
