from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.partner_nachweis import PartnerNachweis
from app.models.vorgang import Vorgang
from app.models.vorgang_event import VorgangEvent

# Ein Partner muss eine Delegation aktiv annehmen oder ablehnen -- kein
# stilles Auto-Zuweisen wie bei einem internen Techniker. Das ist bewusst so
# gewaehlt: ein Nachunternehmer, der ohne jede Widerspruchsmoeglichkeit exakt
# wie ein Angestellter disponiert wird, ist ein Risikofaktor bei einer
# Scheinselbststaendigkeits-Pruefung (Kriterienkatalog der Deutschen
# Rentenversicherung). Dieselbe Uebergangstabellen-Idee wie
# app/services/angebot_service.GUELTIGE_UEBERGAENGE.
GUELTIGE_UEBERGAENGE = {"vorgeschlagen": {"angenommen", "abgelehnt"}}


async def partner_hat_gueltige_freistellungsbescheinigung(
    session: AsyncSession, partner_id: UUID
) -> bool:
    """Prueft, ob eine nicht abgelaufene Freistellungsbescheinigung nach
    § 48 EStG hinterlegt ist. Fehlt sie oder ist sie abgelaufen, muss bei
    Zahlungen fuer Bauleistungen grundsaetzlich 15% Bauabzugsteuer
    einbehalten werden -- das entscheidet hier bewusst niemand automatisch
    (kein hartes Blockieren der Zuweisung), Kaufleute/Steuerberater kennen
    den Einzelfall besser. Der Aufrufer (siehe partner.py:
    partner_zuweisen) gibt das Ergebnis nur als Warnung mit."""
    heute = date.today()
    result = await session.execute(
        select(PartnerNachweis).where(
            PartnerNachweis.partner_id == partner_id,
            PartnerNachweis.typ == "freistellungsbescheinigung",
        )
    )
    nachweise = result.scalars().all()
    return any(n.gueltig_bis is None or n.gueltig_bis >= heute for n in nachweise)


async def apply_partner_status_transition(
    session: AsyncSession,
    vorgang: Vorgang,
    neuer_status: str,
    *,
    mandant_id: UUID,
    actor_partner_zugang_id: UUID | None,
    ablehnung_grund: str | None = None,
) -> None:
    """Verarbeitet die Annahme/Ablehnung einer Vorgang-Delegation durch den
    Partner. Anders als beim internen Vorgang-Status (vorgang.status) wird
    hier NICHT der Vorgang-Status selbst veraendert -- eine Ablehnung
    bedeutet "Partner uebernimmt das nicht", nicht automatisch "Vorgang
    storniert"; die Disposition muss aktiv neu entscheiden (siehe
    app/api/routes/partner.py)."""
    aktueller_status = vorgang.partner_freigabe_status
    if neuer_status not in GUELTIGE_UEBERGAENGE.get(aktueller_status or "", set()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Statuswechsel von '{aktueller_status}' nach '{neuer_status}' nicht erlaubt",
        )

    vorgang.partner_freigabe_status = neuer_status
    if neuer_status == "abgelehnt":
        vorgang.partner_ablehnung_grund = ablehnung_grund

    if neuer_status == "angenommen":
        body = "Nachunternehmer hat den Auftrag angenommen"
    else:
        body = "Nachunternehmer hat abgelehnt"
        if ablehnung_grund:
            body += f": {ablehnung_grund}"
    session.add(
        VorgangEvent(
            mandant_id=mandant_id,
            vorgang_id=vorgang.id,
            event_type="system",
            is_system=True,
            body=body,
            payload={
                "partner_freigabe_status": neuer_status,
                "partner_zugang_id": str(actor_partner_zugang_id) if actor_partner_zugang_id else None,
            },
        )
    )
    vorgang.last_activity_at = datetime.now(timezone.utc)
