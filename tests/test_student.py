"""Offline tests for the manual `/students stash|pop` coordination (no Discord, no database)."""

import asyncio
from types import SimpleNamespace

import pytest

from Coordination import student as student_coord
from Utils import archive as archive_mod
from Utils import channel_moves
from Utils import environment
from Utils.channel_moves import get_guild_lock
from tests.archive_fakes import FakeArchiveTable, FakeGuild, server_error


TEACHER_ID = 1
TEACHER_CATEGORY_ID = 100
ARCHIVE_A = 200
ARCHIVE_B = 300
STUDENT_ROLE = object()


@pytest.fixture
def world(monkeypatch):
    guild = FakeGuild()
    table = FakeArchiveTable()
    guild.add_category(TEACHER_CATEGORY_ID, 'Lehrer')
    guild.add_category(ARCHIVE_A, '📚 Wissensbereich')
    guild.add_category(ARCHIVE_B, '🗃️ Wissenskammer')
    table.rows[ARCHIVE_A] = '📚 Wissensbereich'
    table.rows[ARCHIVE_B] = '🗃️ Wissenskammer'
    connections = {}

    def add_student(student_id, category_id):
        channel = guild.add_channel(student_id, f'schueler-{student_id}', category_id)
        connections[student_id] = SimpleNamespace(student_id=student_id, channel_id=channel.id, teacher_id=TEACHER_ID)
        member = SimpleNamespace(id=student_id, roles=[STUDENT_ROLE], mention=f'<@{student_id}>')
        return member, channel

    monkeypatch.setattr(archive_mod, 'Archive', table)
    monkeypatch.setattr(channel_moves, 'TRANSIENT_RETRY_DELAY', 0)
    monkeypatch.setattr(environment, 'get_student_role', lambda g: STUDENT_ROLE)
    monkeypatch.setattr(environment, 'is_member_archived', lambda m: False)
    monkeypatch.setattr(student_coord, 'TeacherStudentConnection',
                        SimpleNamespace(find_by_student=lambda g, s: connections.get(s)))
    monkeypatch.setattr(student_coord, 'Teacher', lambda g, t: SimpleNamespace(teaching_category=TEACHER_CATEGORY_ID))

    interaction = SimpleNamespace(guild=guild, user=SimpleNamespace(id=TEACHER_ID, mention=f'<@{TEACHER_ID}>'))
    return SimpleNamespace(guild=guild, table=table, add_student=add_student, interaction=interaction)


def test_manual_stash_never_overfills_with_lagging_cache(world):
    world.guild.fill(ARCHIVE_A, 49, start=2000)
    first, first_channel = world.add_student(21, TEACHER_CATEGORY_ID)
    second, second_channel = world.add_student(22, TEACHER_CATEGORY_ID)

    async def stash_both():
        await student_coord.stash_student(world.interaction, first)
        await student_coord.stash_student(world.interaction, second)  # The cache still shows 49 in A

    asyncio.run(stash_both())

    assert world.guild.server_parent[first_channel.id] == ARCHIVE_A
    assert world.guild.server_parent[second_channel.id] == ARCHIVE_B
    assert len(world.guild.edit_calls) == 2


def test_manual_stash_holds_the_guild_lock(world):
    member, channel = world.add_student(21, TEACHER_CATEGORY_ID)
    lock_states = []
    original_edit = channel.edit

    async def recording_edit(**kwargs):
        lock_states.append(get_guild_lock(world.guild.id).locked())
        return await original_edit(**kwargs)
    channel.edit = recording_edit

    asyncio.run(student_coord.stash_student(world.interaction, member))

    assert lock_states == [True]
    assert world.guild.server_parent[channel.id] == ARCHIVE_A


def test_manual_pop_holds_the_guild_lock(world, monkeypatch):
    monkeypatch.setattr(environment, 'is_member_archived', lambda m: True)
    member, channel = world.add_student(21, ARCHIVE_A)
    lock_states = []
    original_edit = channel.edit

    async def recording_edit(**kwargs):
        lock_states.append(get_guild_lock(world.guild.id).locked())
        return await original_edit(**kwargs)
    channel.edit = recording_edit

    asyncio.run(student_coord.pop_student(world.interaction, member))

    assert lock_states == [True]
    assert world.guild.server_parent[channel.id] == TEACHER_CATEGORY_ID


def test_manual_pop_retries_transient_error_once(world, monkeypatch):
    monkeypatch.setattr(environment, 'is_member_archived', lambda m: True)
    member, channel = world.add_student(21, ARCHIVE_A)
    world.guild.fail_edits = [server_error()]

    asyncio.run(student_coord.pop_student(world.interaction, member))

    assert world.guild.edit_calls == [(channel.id, TEACHER_CATEGORY_ID)] * 2
    assert world.guild.server_parent[channel.id] == TEACHER_CATEGORY_ID


def test_deprecated_get_archive_channel_skips_full_archive(world):
    # Archive A is full on Discord, but the gateway events of those moves have not reached the cache yet
    for channel in world.guild.fill(ARCHIVE_A, 50, start=2000):
        channel.category_id = TEACHER_CATEGORY_ID
    assert len(world.guild.categories[1].channels) == 0

    with pytest.warns(DeprecationWarning):
        category = asyncio.run(environment.get_archive_channel(world.guild))

    assert category.id == ARCHIVE_B
