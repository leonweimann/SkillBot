"""Offline tests for cogs.AutoPop (no Discord, no database)."""

import asyncio
from types import SimpleNamespace

import pytest

from cogs import AutoPop as auto_pop
from Coordination import daily_prep as auto_pop_helpers
from cogs.AutoPop import AutoPop, joined_lounge, resolve_student_id

ARCHIVE_ID = 200
TEACHER_CAT_ID = 100


def vc(id, name):
    return SimpleNamespace(id=id, name=name)


LOUNGE = vc(1, 'lounge')
OTHER = vc(2, 'klassenzimmer')


# region joined_lounge

@pytest.mark.parametrize('before, after, expected', [
    (None, LOUNGE, True),  # fresh join
    (OTHER, LOUNGE, True),  # switch from another channel
    (LOUNGE, LOUNGE, False),  # mute/deafen/stream toggle
    (LOUNGE, None, False),  # leaving
    (LOUNGE, OTHER, False),  # moved out of the lounge
    (None, OTHER, False),  # other channel name
    (None, None, False),
])
def test_joined_lounge(before, after, expected):
    assert joined_lounge(before, after) is expected

# endregion


# region resolve_student_id

def test_resolve_student_id(monkeypatch):
    monkeypatch.setattr(auto_pop_helpers.Subuser, 'get_user_of_subuser',
                        lambda guild_id, member_id: SimpleNamespace(id=7) if member_id == 99 else None)
    assert resolve_student_id(5, 99) == 7
    assert resolve_student_id(5, 42) == 42

# endregion


# region listener

class FakeChannel:
    def __init__(self, category_id):
        self.category_id = category_id
        self.name = 'anna'
        self.mention = '<#11>'


@pytest.fixture
def run(monkeypatch):
    calls = []
    logs = []

    looked_up = []
    reasons = []

    async def fake_pop(guild, ts_con, reason=None):
        calls.append(ts_con)
        reasons.append(reason)
        return True

    async def fake_log(guild, message, fields=None):
        logs.append(message)

    monkeypatch.setattr(auto_pop, 'pop_to_teacher', fake_pop)
    monkeypatch.setattr(auto_pop, 'log', fake_log)
    monkeypatch.setattr(auto_pop, 'is_archived_category', lambda guild, cid: cid == ARCHIVE_ID)
    def _run(channel_category, ts_con, main_user_id=None):
        main_user = SimpleNamespace(id=main_user_id) if main_user_id else None
        monkeypatch.setattr(auto_pop_helpers.Subuser, 'get_user_of_subuser', lambda g, m: main_user)

        def find_by_student(guild_id, student_id):
            looked_up.append(student_id)
            return ts_con
        monkeypatch.setattr(auto_pop.TeacherStudentConnection, 'find_by_student', find_by_student)
        guild = SimpleNamespace(id=5, name='g', get_channel=lambda cid: FakeChannel(channel_category))
        member = SimpleNamespace(id=3, bot=False, guild=guild, mention='<@3>')
        before = SimpleNamespace(channel=None)
        after = SimpleNamespace(channel=LOUNGE)
        asyncio.run(AutoPop(None).on_voice_state_update(member, before, after))
        return calls, logs, looked_up, reasons

    return _run


TS_CON = SimpleNamespace(channel_id=11, teacher_id=1)


def test_archived_student_joining_lounge_is_popped(run):
    calls, logs, looked_up, reasons = run(ARCHIVE_ID, TS_CON)
    assert calls == [TS_CON]
    assert looked_up == [3]  # the joining member itself
    assert reasons == ['Auto-Pop: Lounge betreten']
    assert len(logs) == 1 and 'Lounge' in logs[0]


def test_sub_account_joining_lounge_pops_main_student(run):
    calls, _, looked_up, _ = run(ARCHIVE_ID, TS_CON, main_user_id=7)
    assert looked_up == [7]
    assert calls == [TS_CON]


def test_channel_already_in_teacher_category_is_ignored(run):
    calls, logs, _, _ = run(TEACHER_CAT_ID, TS_CON)
    assert calls == []
    assert logs == []


def test_non_student_is_ignored(run):
    calls, logs, _, _ = run(ARCHIVE_ID, None)
    assert calls == []
    assert logs == []  # no swallowed error either

# endregion
