import asyncio
from collections.abc import Awaitable
from typing import TypeVar

T = TypeVar("T")


async def run_with_timeout(operation: Awaitable[T], timeout_seconds: float) -> T:
    return await asyncio.wait_for(operation, timeout_seconds)
