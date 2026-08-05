from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification
from app.models.vorgang_anfrage import VorgangAnfrage
from app.services.event_bus import event_bus
from app.services.zuweisung_service import dispo_verantwortliche_user_ids


async def notify_neue_anfrage(
    session: AsyncSession, *, mandant_id: UUID, anfrage: VorgangAnfrage, kunde_name: str
) -> None:
    """Benachrichtigt alle disposition-berechtigten Nutzer/Mandanten-Admins
    des Mandanten ueber eine neu eingegangene Kundenportal-Auftragsanfrage --
    sonst faellt eine solche Anfrage niemandem auf, bis jemand zufaellig die
    Liste oeffnet."""
    empfaenger_ids = list(await dispo_verantwortliche_user_ids(session, mandant_id))

    for user_id in empfaenger_ids:
        session.add(
            Notification(
                mandant_id=mandant_id,
                user_id=user_id,
                typ="anfrage",
                titel=f"Neue Auftragsanfrage von {kunde_name}: {anfrage.titel}",
                ref_entity_type="vorgang_anfrage",
                ref_entity_id=anfrage.id,
            )
        )
    await session.flush()

    await event_bus.publish(
        mandant_id,
        "notification",
        {"typ": "anfrage", "vorgang_anfrage_id": str(anfrage.id)},
    )
