from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification
from app.models.user import User
from app.models.vorgang_anfrage import VorgangAnfrage
from app.services.event_bus import event_bus


async def notify_neue_anfrage(
    session: AsyncSession, *, mandant_id: UUID, anfrage: VorgangAnfrage, kunde_name: str
) -> None:
    """Benachrichtigt alle Disponenten/Mandanten-Admins des Mandanten ueber
    eine neu eingegangene Kundenportal-Auftragsanfrage -- sonst faellt eine
    solche Anfrage niemandem auf, bis jemand zufaellig die Liste oeffnet."""
    empfaenger_result = await session.execute(
        select(User.id).where(
            User.mandant_id == mandant_id,
            User.role.in_(("mandant_admin", "disponent")),
            User.aktiv.is_(True),
        )
    )
    empfaenger_ids = list(empfaenger_result.scalars().all())

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
