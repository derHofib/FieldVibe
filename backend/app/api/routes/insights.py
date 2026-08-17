from datetime import datetime, time, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_db, require_module, require_roles
from app.models.angebot import Angebot
from app.models.eingangsrechnung import Eingangsrechnung
from app.models.rechnung import Rechnung
from app.models.user import User
from app.models.vorgang import Vorgang
from app.models.zeiterfassung import Zeiterfassung
from app.schemas.insights import Insights, TechnikerAuslastung
from app.services import eingangsrechnung_service
from app.services.rechnung_service import bezahlter_betrag, brutto_betrag, positionen_fuer, zahlungen_fuer
from app.services.zuweisung_service import technik_user_ids

router = APIRouter(
    prefix="/api/insights",
    tags=["insights"],
    dependencies=[
        Depends(require_roles("mandant_admin")),
        Depends(require_module("statistik")),
    ],
)


def _montag_dieser_woche(jetzt: datetime) -> datetime:
    tage_seit_montag = jetzt.weekday()
    montag_datum = jetzt.date() - timedelta(days=tage_seit_montag)
    return datetime.combine(montag_datum, time.min, tzinfo=timezone.utc)


@router.get("", response_model=Insights)
async def get_insights(
    auth: AuthContext = Depends(get_current_user), session: AsyncSession = Depends(get_db)
) -> Insights:
    status_result = await session.execute(
        select(Vorgang.status, func.count()).group_by(Vorgang.status)
    )
    vorgaenge_nach_status = {status: count for status, count in status_result.all()}

    offene_rechnungen = (
        await session.execute(
            select(Rechnung).where(Rechnung.status.in_(("entwurf", "versendet", "teilweise_bezahlt")))
        )
    ).scalars().all()
    # brutto_betrag() minus bereits gebuchter Zahlungen statt des vollen
    # Bruttobetrags -- sonst zaehlt eine zu 90% bezahlte Rechnung (Status
    # teilweise_bezahlt) hier weiterhin mit ihrem vollen Betrag mit.
    offene_rechnungssumme = Decimal("0")
    for r in offene_rechnungen:
        positionen = await positionen_fuer(session, r.id)
        zahlungen = await zahlungen_fuer(session, r.id)
        offene_rechnungssumme += brutto_betrag(r, positionen) - bezahlter_betrag(zahlungen)
    offene_rechnungssumme = offene_rechnungssumme.quantize(Decimal("0.01"))

    offene_eingangsrechnungen = (
        await session.execute(select(Eingangsrechnung).where(Eingangsrechnung.status == "offen"))
    ).scalars().all()
    offene_verbindlichkeiten = Decimal("0")
    for e in offene_eingangsrechnungen:
        positionen = await eingangsrechnung_service.positionen_fuer(session, e.id)
        zahlungen = await eingangsrechnung_service.zahlungen_fuer(session, e.id)
        brutto = eingangsrechnung_service.brutto_betrag(e, positionen)
        offene_verbindlichkeiten += brutto - eingangsrechnung_service.bezahlter_betrag(zahlungen)
    offene_verbindlichkeiten = offene_verbindlichkeiten.quantize(Decimal("0.01"))

    angebote_versendet = (
        await session.scalar(select(func.count()).select_from(Angebot).where(Angebot.versendet_am.isnot(None)))
    ) or 0
    angebote_angenommen = (
        await session.scalar(select(func.count()).select_from(Angebot).where(Angebot.status == "angenommen"))
    ) or 0
    angebote_annahmequote = (
        angebote_angenommen / angebote_versendet if angebote_versendet > 0 else None
    )

    wochenstart = _montag_dieser_woche(datetime.now(timezone.utc))
    techniker_ids = await technik_user_ids(session, auth.mandant_id)
    technikers = (
        await session.execute(
            select(User).where(User.id.in_(techniker_ids), User.aktiv.is_(True)).order_by(User.name)
        )
    ).scalars().all()

    techniker_auslastung: list[TechnikerAuslastung] = []
    for techniker in technikers:
        eintraege = (
            await session.execute(
                select(Zeiterfassung).where(
                    Zeiterfassung.techniker_id == techniker.id,
                    Zeiterfassung.start_at >= wochenstart,
                    Zeiterfassung.ende_at.isnot(None),
                )
            )
        ).scalars().all()
        sekunden = sum((e.ende_at - e.start_at).total_seconds() for e in eintraege)
        stunden = (Decimal(sekunden) / Decimal(3600)).quantize(Decimal("0.1"))
        techniker_auslastung.append(
            TechnikerAuslastung(techniker_id=techniker.id, name=techniker.name, stunden_diese_woche=stunden)
        )

    return Insights(
        vorgaenge_nach_status=vorgaenge_nach_status,
        offene_rechnungssumme=offene_rechnungssumme,
        offene_verbindlichkeiten=offene_verbindlichkeiten,
        angebote_versendet=angebote_versendet,
        angebote_angenommen=angebote_angenommen,
        angebote_annahmequote=angebote_annahmequote,
        techniker_auslastung=techniker_auslastung,
    )
