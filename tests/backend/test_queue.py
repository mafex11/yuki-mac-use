import asyncio
import pytest
from yuki.backend.queue import ControlQueue


async def test_serializes_tasks():
    q = ControlQueue()
    order = []

    async def job(name):
        order.append(f"start-{name}")
        await asyncio.sleep(0.05)
        order.append(f"end-{name}")
        return name

    h1 = await q.submit(lambda: job("a"))
    h2 = await q.submit(lambda: job("b"))
    r1 = await h1
    r2 = await h2
    assert r1 == "a" and r2 == "b"
    assert order == ["start-a", "end-a", "start-b", "end-b"]


async def test_depth_reports_waiting():
    q = ControlQueue()

    async def slow():
        await asyncio.sleep(0.1)

    await q.submit(slow)
    await q.submit(slow)
    assert q.depth() >= 1


async def test_job_exception_propagates():
    q = ControlQueue()

    async def boom():
        raise ValueError("test")

    fut = await q.submit(boom)
    with pytest.raises(ValueError, match="test"):
        await fut
    assert q.depth() == 0
