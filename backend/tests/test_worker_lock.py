import pytest

from app.services.worker_lock import worker_lock


@pytest.mark.asyncio
async def test_second_concurrent_lock_attempt_fails_while_first_holds_it():
    async with worker_lock() as first_acquired:
        assert first_acquired is True

        async with worker_lock() as second_acquired:
            assert second_acquired is False


@pytest.mark.asyncio
async def test_lock_is_available_again_after_release():
    async with worker_lock() as first_acquired:
        assert first_acquired is True

    async with worker_lock() as second_acquired:
        assert second_acquired is True
