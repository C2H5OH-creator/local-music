import asyncio
from collections.abc import Callable
from typing import TypeVar

from api.settings import get_settings


T = TypeVar("T")


async def run_blocking_yandex_call(
    func: Callable[..., T],
    *args,
    timeout: int | None = None,
) -> T:
    settings = get_settings()
    return await asyncio.wait_for(
        asyncio.to_thread(func, *args),
        timeout=timeout or settings.yandex_music_request_timeout,
    )
