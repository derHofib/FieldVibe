import asyncio
import json
from collections import defaultdict
from typing import Any
from uuid import UUID

# In-process pub/sub for SSE (/api/stream). Deliberately simple: one
# asyncio.Queue per connected client, keyed by mandant_id. This only works
# within a single backend process/container -- horizontally scaling the
# backend would need a shared broker (Postgres LISTEN/NOTIFY or Redis) so
# every instance's subscribers see every publish. Fine for the current
# docker-compose topology (one backend container); documented as a known
# limitation for later.


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[UUID, set[asyncio.Queue]] = defaultdict(set)

    def subscribe(self, mandant_id: UUID) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers[mandant_id].add(queue)
        return queue

    def unsubscribe(self, mandant_id: UUID, queue: asyncio.Queue) -> None:
        self._subscribers[mandant_id].discard(queue)
        if not self._subscribers[mandant_id]:
            self._subscribers.pop(mandant_id, None)

    async def publish(self, mandant_id: UUID, event: str, data: dict[str, Any]) -> None:
        for queue in list(self._subscribers.get(mandant_id, ())):
            try:
                queue.put_nowait({"event": event, "data": json.dumps(data, default=str)})
            except asyncio.QueueFull:
                pass  # slow consumer: drop rather than block the publisher


event_bus = EventBus()
