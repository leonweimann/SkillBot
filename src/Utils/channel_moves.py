"""
Shared helpers for moving channels between categories.

`get_guild_lock` serialises all channel moves within a guild (nightly preparation, auto-pop and the
manual `/students stash|pop` commands). `retry_transient` repeats a Discord call once if it failed for a
transient network or server reason.

This module only depends on discord.py, so every coordinator can import it without import cycles.
"""

import asyncio
from typing import Awaitable, Callable, TypeVar

import aiohttp
import discord


T = TypeVar('T')

TRANSIENT_RETRY_DELAY = 2.0  # Seconds to wait before the single retry of a transient failure

_TRANSIENT_ERRORS = (discord.DiscordServerError, aiohttp.ClientError, OSError, asyncio.TimeoutError)

_guild_locks: dict[int, asyncio.Lock] = {}


def get_guild_lock(guild_id: int) -> asyncio.Lock:
    """
    Returns the lock that serialises all channel moves within a guild.

    Args:
        guild_id (int): The ID of the guild.

    Returns:
        asyncio.Lock: The same lock instance for every call with the same guild ID.
    """
    lock = _guild_locks.get(guild_id)
    if lock is None:
        lock = _guild_locks[guild_id] = asyncio.Lock()
    return lock


def is_transient_error(error: BaseException) -> bool:
    """
    Checks whether a failed Discord call is worth repeating.

    Transient are 5xx responses of Discord, aiohttp client errors (e.g. a server disconnect), OS level
    connection errors (e.g. a connection reset, which discord.py only retries on macOS/Windows) and
    timeouts. Client errors like 400/403/404 are never transient.

    Args:
        error (BaseException): The error raised by the Discord call.

    Returns:
        bool: True if repeating the call might succeed.
    """
    return isinstance(error, _TRANSIENT_ERRORS)


async def retry_transient(call: Callable[[], Awaitable[T]], *, delay: float | None = None) -> T:
    """
    Awaits ``call()`` and repeats it once after a short delay if it failed transiently.

    Only use this for idempotent calls: if the first attempt reached Discord before the connection broke,
    the call is sent a second time (moving a channel into the same category again is harmless).

    Args:
        call (Callable[[], Awaitable[T]]): Creates the awaitable to run (called once per attempt).
        delay (float | None): Seconds to wait before the retry. Defaults to ``TRANSIENT_RETRY_DELAY``.

    Returns:
        T: The result of the successful attempt.

    Raises:
        Exception: The error of the second attempt, or the first error if it was not transient.
    """
    try:
        return await call()
    except Exception as e:
        if not is_transient_error(e):
            raise
        print(f'[channel_moves] Transient error, retrying once: {e!r}')
    await asyncio.sleep(TRANSIENT_RETRY_DELAY if delay is None else delay)
    return await call()
