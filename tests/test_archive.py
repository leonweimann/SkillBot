"""Offline tests for Utils.archive (no Discord, no database).

The fake guild (tests.archive_fakes) enforces Discord's 50 channel limit per category on the "server" and
has a guild cache that never catches up during a burst of moves.
"""

import asyncio
from types import SimpleNamespace

import discord
import pytest

from Utils import archive as archive_mod
from Utils import channel_moves
from Utils.archive import ArchiveAllocator, is_category_full_error
from tests.archive_fakes import MAX, FakeArchiveTable, FakeGuild, category_full_error, http_error, server_error


TEACHER_CATEGORY_ID = 100
ARCHIVE_A = 200
ARCHIVE_B = 300


# region Fixtures

@pytest.fixture
def world(monkeypatch):
    guild = FakeGuild()
    table = FakeArchiveTable()
    guild.add_category(TEACHER_CATEGORY_ID, 'Lehrer')
    guild.add_category(ARCHIVE_A, '📚 Wissensbereich')
    table.rows[ARCHIVE_A] = '📚 Wissensbereich'
    monkeypatch.setattr(archive_mod, 'Archive', table)
    monkeypatch.setattr(channel_moves, 'TRANSIENT_RETRY_DELAY', 0)
    return SimpleNamespace(guild=guild, table=table)


def add_archive_b(world, filled):
    world.guild.add_category(ARCHIVE_B, '🗃️ Wissenskammer')
    world.table.rows[ARCHIVE_B] = '🗃️ Wissenskammer'
    world.guild.fill(ARCHIVE_B, filled, start=3000)


def students(world, count):
    return world.guild.fill(TEACHER_CATEGORY_ID, count, start=1)


async def archive_all(guild, channels):
    allocator = await ArchiveAllocator.create(guild)
    return [(await allocator.archive(channel)).id for channel in channels]

# endregion


# region is_category_full_error

def test_detects_category_full_error():
    assert is_category_full_error(category_full_error())


def test_detects_category_full_error_from_text_only():
    error = http_error(400, 50035, message='Invalid Form Body')
    error.text = 'Invalid Form Body\nIn parent_id: Maximum number of channels in category reached (50)'
    error._errors = None
    assert is_category_full_error(error)


@pytest.mark.parametrize('error', [
    http_error(403, 50013, message='Missing Permissions'),
    http_error(400, 50035, {'name': {'_errors': [{'code': 'BASE_TYPE_BAD_LENGTH', 'message': 'Must be 1-100'}]}}),
    http_error(404, 10003, message='Unknown Channel'),
    RuntimeError('parent_id'),
])
def test_other_errors_are_not_category_full(error):
    assert not is_category_full_error(error)

# endregion


# region ArchiveAllocator

def test_archive_at_49_overflows_into_next_archive_with_lagging_cache(world):
    world.guild.fill(ARCHIVE_A, 49, start=2000)
    add_archive_b(world, filled=10)
    channels = students(world, 5)

    targets = asyncio.run(archive_all(world.guild, channels))

    assert targets == [ARCHIVE_A] + [ARCHIVE_B] * 4
    assert world.guild.server_count(ARCHIVE_A) == MAX
    assert world.guild.server_count(ARCHIVE_B) == 14
    assert len(world.guild.edit_calls) == 5  # no rejected move at all
    assert world.guild.fetches == 1
    assert world.guild.created == []


def test_legacy_cache_based_archive_overfills_with_lagging_cache(world):
    """Documents the original bug: the cache-based ArchiveCategory picks the full archive again."""
    world.guild.fill(ARCHIVE_A, 49, start=2000)
    add_archive_b(world, filled=10)
    first, second = students(world, 2)

    async def legacy():
        await (await archive_mod.ArchiveCategory.make(world.guild)).add_channel(first)
        await (await archive_mod.ArchiveCategory.make(world.guild)).add_channel(second)

    with pytest.raises(discord.HTTPException) as excinfo:
        asyncio.run(legacy())
    assert is_category_full_error(excinfo.value)


def test_all_archives_full_creates_and_uses_new_archive(world):
    world.guild.fill(ARCHIVE_A, MAX, start=2000)
    add_archive_b(world, filled=MAX)
    channels = students(world, 3)

    targets = asyncio.run(archive_all(world.guild, channels))

    assert world.guild.created == ['🗄️ Wissensspeicher']
    new_id = next(id for id, name in world.table.rows.items() if name == '🗄️ Wissensspeicher')
    assert targets == [new_id] * 3
    assert world.guild.server_count(new_id) == 3
    assert world.guild.server_count(ARCHIVE_A) == MAX and world.guild.server_count(ARCHIVE_B) == MAX


def test_new_archive_fills_up_and_rolls_over_again(world):
    world.guild.fill(ARCHIVE_A, MAX, start=2000)
    channels = students(world, MAX + 2)

    targets = asyncio.run(archive_all(world.guild, channels))

    assert world.guild.created == ['🗃️ Wissenskammer', '🗄️ Wissensspeicher']
    assert len(set(targets)) == 2
    assert all(world.guild.server_count(id) <= MAX for id in world.guild.server_categories)
    assert sorted(targets.count(t) for t in set(targets)) == [2, MAX]


def test_full_rejection_from_server_is_retried_in_next_archive(world):
    world.guild.fill(ARCHIVE_A, 48, start=2000)
    add_archive_b(world, filled=0)
    channel = students(world, 1)[0]

    async def scenario():
        allocator = await ArchiveAllocator.create(world.guild)
        # Someone else fills archive A after the fetch: the fetched counts are outdated
        world.guild.fill(ARCHIVE_A, 2, start=4000)
        return await allocator.archive(channel), allocator

    target, allocator = asyncio.run(scenario())

    assert target.id == ARCHIVE_B
    assert world.guild.edit_calls == [(channel.id, ARCHIVE_A), (channel.id, ARCHIVE_B)]
    assert allocator.count(ARCHIVE_A) == MAX
    assert world.guild.server_parent[channel.id] == ARCHIVE_B


def test_full_rejection_of_only_archive_creates_new_one(world):
    world.guild.fill(ARCHIVE_A, 49, start=2000)
    channel = students(world, 1)[0]

    async def scenario():
        allocator = await ArchiveAllocator.create(world.guild)
        world.guild.fill(ARCHIVE_A, 1, start=4000)
        return await allocator.archive(channel)

    target = asyncio.run(scenario())

    assert world.guild.created == ['🗃️ Wissenskammer']
    assert world.guild.server_parent[channel.id] == target.id != ARCHIVE_A


def test_transient_error_is_retried_once(world):
    channel = students(world, 1)[0]
    world.guild.fail_edits = [server_error()]

    target = asyncio.run(archive_all(world.guild, [channel]))

    assert target == [ARCHIVE_A]
    assert world.guild.edit_calls == [(channel.id, ARCHIVE_A)] * 2


def test_connection_reset_is_retried_once(world):
    channel = students(world, 1)[0]
    world.guild.fail_edits = [ConnectionResetError(104, 'Connection reset by peer')]

    assert asyncio.run(archive_all(world.guild, [channel])) == [ARCHIVE_A]
    assert len(world.guild.edit_calls) == 2


def test_transient_fetch_error_is_retried_once(world):
    channel = students(world, 1)[0]
    world.guild.fail_fetches = [server_error()]

    assert asyncio.run(archive_all(world.guild, [channel])) == [ARCHIVE_A]
    assert world.guild.fetches == 2


def test_second_transient_error_is_raised(world):
    channel = students(world, 1)[0]
    world.guild.fail_edits = [server_error(), server_error()]

    with pytest.raises(discord.DiscordServerError):
        asyncio.run(archive_all(world.guild, [channel]))
    assert len(world.guild.edit_calls) == 2


def test_non_capacity_error_is_not_retried(world):
    add_archive_b(world, filled=0)
    channel = students(world, 1)[0]
    world.guild.fail_edits = [http_error(403, 50013, message='Missing Permissions')]

    with pytest.raises(discord.HTTPException) as excinfo:
        asyncio.run(archive_all(world.guild, [channel]))

    assert excinfo.value.code == 50013
    assert world.guild.edit_calls == [(channel.id, ARCHIVE_A)]


def test_retries_are_bounded_when_every_archive_rejects(world):
    channel = students(world, 1)[0]
    world.guild.fail_edits = [category_full_error() for _ in range(20)]

    with pytest.raises(discord.HTTPException):
        asyncio.run(archive_all(world.guild, [channel]))

    assert len(world.guild.edit_calls) == ArchiveAllocator.MAX_FULL_RETRIES + 1


def test_channel_already_in_archive_is_not_moved(world):
    archived = world.guild.add_channel(7, 'schon-archiviert', ARCHIVE_A)

    assert asyncio.run(archive_all(world.guild, [archived])) == [ARCHIVE_A]
    assert world.guild.edit_calls == []


def test_deleted_archive_is_ignored(world):
    world.table.rows[999] = '📦 Lehrarchiv'  # Row without a category on Discord
    channel = students(world, 1)[0]

    assert asyncio.run(archive_all(world.guild, [channel])) == [ARCHIVE_A]


def test_unknown_categories_are_not_counted_as_archives(world):
    world.guild.fill(TEACHER_CATEGORY_ID, 60, start=5000)
    channel = students(world, 1)[0]

    allocator = asyncio.run(ArchiveAllocator.create(world.guild))
    assert [a.id for a in allocator.archives] == [ARCHIVE_A]
    assert allocator.count(TEACHER_CATEGORY_ID) == 61
    assert asyncio.run(allocator.archive(channel)).id == ARCHIVE_A

# endregion


# region _create_new_archive_category

def test_reused_same_name_category_gets_registered(world):
    world.guild.add_category(777, '🗃️ Wissenskammer')  # Exists on Discord, but has no archive row

    category = asyncio.run(archive_mod.ArchiveCategory._create_new_archive_category(world.guild))

    assert category.id == 777
    assert world.guild.created == []
    assert world.table.rows[777] == '🗃️ Wissenskammer'


def test_reused_full_category_is_skipped_by_allocator(world):
    world.guild.fill(ARCHIVE_A, MAX, start=2000)
    world.guild.add_category(777, '🗃️ Wissenskammer')  # Unregistered and already full
    world.guild.fill(777, MAX, start=6000)
    channel = students(world, 1)[0]

    target = asyncio.run(archive_all(world.guild, [channel]))

    assert world.table.rows[777] == '🗃️ Wissenskammer'
    assert world.guild.created == ['🗄️ Wissensspeicher']
    assert target != [777]
    assert world.guild.server_count(777) == MAX

# endregion
