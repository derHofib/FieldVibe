"""Unit-level coverage for the SSE pub/sub primitive itself (deterministic,
unlike driving it end-to-end over a streaming HTTP response in the same
test-process event loop -- see test_stream.py for the auth-guard tests on
the actual /api/stream endpoint)."""

import uuid

import pytest

from app.services.event_bus import EventBus


@pytest.mark.asyncio
async def test_publish_delivers_to_subscriber():
    bus = EventBus()
    mandant_id = uuid.uuid4()
    queue = bus.subscribe(mandant_id)

    await bus.publish(mandant_id, "vorgang_event", {"foo": "bar"})

    item = queue.get_nowait()
    assert item["event"] == "vorgang_event"
    assert "bar" in item["data"]


@pytest.mark.asyncio
async def test_publish_does_not_leak_across_mandanten():
    bus = EventBus()
    mandant_a, mandant_b = uuid.uuid4(), uuid.uuid4()
    queue_a = bus.subscribe(mandant_a)
    queue_b = bus.subscribe(mandant_b)

    await bus.publish(mandant_a, "vorgang_event", {})

    assert queue_a.qsize() == 1
    assert queue_b.qsize() == 0


@pytest.mark.asyncio
async def test_unsubscribe_stops_delivery():
    bus = EventBus()
    mandant_id = uuid.uuid4()
    queue = bus.subscribe(mandant_id)
    bus.unsubscribe(mandant_id, queue)

    await bus.publish(mandant_id, "vorgang_event", {})

    assert queue.qsize() == 0
