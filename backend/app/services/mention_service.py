import re
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification
from app.models.user import User
from app.models.vorgang import Vorgang
from app.services.event_bus import event_bus

# The frontend's @-mention picker inserts "@[Name](user-id)" into the
# comment body -- unambiguous to parse, unlike matching on display names
# (which can collide) or bare emails (awkward once you consider the body
# text itself may contain an unrelated "@" character).
_MENTION_RE = re.compile(
    r"@\[[^\]]+\]\(([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\)"
)


async def extract_and_notify_mentions(
    session: AsyncSession,
    *,
    mandant_id: UUID,
    vorgang: Vorgang,
    body: str,
    actor_user_id: UUID,
) -> None:
    mentioned_ids = {UUID(m) for m in _MENTION_RE.findall(body)}
    mentioned_ids.discard(actor_user_id)  # niemand benachrichtigt sich selbst
    if not mentioned_ids:
        return

    for user_id in mentioned_ids:
        # session.get is RLS-scoped: a mention of a user from another
        # mandant (typo'd id, stale client state) simply resolves to
        # nothing rather than silently notifying a stranger.
        mentioned_user = await session.get(User, user_id)
        if mentioned_user is None:
            continue

        session.add(
            Notification(
                mandant_id=mandant_id,
                user_id=user_id,
                typ="mention",
                titel=f"Erwähnt in {vorgang.vorgangsnummer}: {vorgang.titel}",
                ref_entity_type="vorgang",
                ref_entity_id=vorgang.id,
            )
        )
        await event_bus.publish(
            mandant_id,
            "notification",
            {
                "typ": "mention",
                "user_id": str(user_id),
                "vorgang_id": str(vorgang.id),
                "vorgangsnummer": vorgang.vorgangsnummer,
            },
        )
