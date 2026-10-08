"""Tests for Coordination.orphans and `/dev orphans` (temp database, Discord fakes)."""

import asyncio
from types import SimpleNamespace

import discord
import pytest

from Coordination import orphans
from Coordination.orphans import MESSAGE_LIMIT, Orphan, OrphanReport, build_report, format_report, run_orphan_cleanup
from Utils.channel_moves import get_guild_lock
from Utils.database import DatabaseManager, Student, Teacher, TeacherStudentConnection, User
from Utils.errors import CodeError

GUILD = 1
TEACHER = 10
GONE, STAYING, NAMELESS, FINE = 20, 21, 22, 23  # Student IDs
CHANNEL = {GONE: 100, STAYING: 101, NAMELESS: 102, FINE: 103}


@pytest.fixture(autouse=True)
def db(tmp_path, monkeypatch):
    path = str(tmp_path / 'test.db')
    monkeypatch.setattr(DatabaseManager, '_DatabaseManager__get_db_path',
                        staticmethod(lambda guild_id: path))
    DatabaseManager.create_tables(GUILD)


@pytest.fixture
def logs(monkeypatch):
    entries = []

    async def fake_log(guild, message, details={}):
        entries.append((message, details))

    monkeypatch.setattr(orphans, 'log', fake_log)
    return entries


def not_found():
    return discord.NotFound(SimpleNamespace(status=404, reason='Not Found'), {'code': 10007, 'message': 'Unknown Member'})


class FakeGuild:
    """Only FINE's channel exists; GONE and NAMELESS left the server, STAYING is only known to Discord."""

    def __init__(self, channel_ids=(CHANNEL[FINE], 999), members=(STAYING, FINE, TEACHER), cached=(TEACHER,)):
        self.id = GUILD
        self.channel_ids = list(channel_ids)
        self.members = set(members)
        self.cached = set(cached)  # get_member only knows these, the rest needs fetch_member
        self.fetch_member_error = None
        self.lock_held_during_fetch = None

    async def fetch_channels(self):
        self.lock_held_during_fetch = get_guild_lock(self.id).locked()
        return [SimpleNamespace(id=cid) for cid in self.channel_ids]

    def get_member(self, user_id):
        return SimpleNamespace(id=user_id) if user_id in self.cached else None

    async def fetch_member(self, user_id):
        if self.fetch_member_error:
            raise self.fetch_member_error
        if user_id not in self.members:
            raise not_found()
        return SimpleNamespace(id=user_id)


class FakeUser:
    id = 1

    def __str__(self):
        return 'dev'


ACTOR = FakeUser()


def seed():
    Teacher(guild_id=GUILD, id=TEACHER).save()
    for student_id, name in ((GONE, 'Max Muster'), (STAYING, 'Anna Bleibt'), (NAMELESS, None), (FINE, 'Fritz Fein')):
        student = Student(guild_id=GUILD, id=student_id)
        student.real_name = name
        student.save()
        TeacherStudentConnection(guild_id=GUILD, teacher_id=TEACHER, student_id=student_id,
                                 channel_id=CHANNEL[student_id]).save()


def connected(student_id):
    return TeacherStudentConnection.find_by_student(GUILD, student_id) is not None


def run(guild, apply):
    return asyncio.run(run_orphan_cleanup(guild, apply=apply, actor=ACTOR))


# region build_report / format_report

def conn(student_id, channel_id):
    return SimpleNamespace(teacher_id=TEACHER, student_id=student_id, channel_id=channel_id)


def test_build_report_classifies_by_channel_and_membership():
    report = build_report([conn(1, 100), conn(2, 101), conn(3, 102)], existing_channel_ids={100},
                          member_ids={2}, names={1: 'A', 2: 'B'})
    assert report.checked == 3
    assert [o.student_id for o in report.departed] == [3]
    assert [o.student_id for o in report.still_members] == [2]
    assert report.departed[0].real_name is None


def test_label_without_name_shows_only_ids():
    assert Orphan(TEACHER, 5, 6).label() == f'Schüler `5`, Lehrer `{TEACHER}`, Channel `6`'
    assert Orphan(TEACHER, 5, 6, 'Max').label().startswith('Max (Schüler `5`')


def test_format_nothing_found():
    assert format_report(OrphanReport(checked=94)).startswith('✅ Keine verwaisten')


def test_format_lists_eleven_orphans_completely():
    report = OrphanReport(checked=94, departed=[Orphan(TEACHER, 1000 + i, 5000 + i, f'Schüler Nummer {i}') for i in range(10)],
                          still_members=[Orphan(TEACHER, 30, 31, 'Anna')])
    message = format_report(report)
    assert 'weitere' not in message
    assert all(f'Schüler Nummer {i}' in message for i in range(10))


def test_format_truncates_long_lists():
    report = OrphanReport(
        checked=400,
        departed=[Orphan(TEACHER, 1000 + i, 5000 + i, f'Schüler Nummer {i}') for i in range(200)],
        still_members=[Orphan(TEACHER, 3000 + i, 7000 + i, f'Bleibt Nummer {i}') for i in range(100)],
    )
    message = format_report(report)
    assert len(message) <= MESSAGE_LIMIT < 2000
    assert 'Würde löschen (200)' in message
    assert 'Nicht gelöscht – Schüler noch auf dem Server (100)' in message
    assert message.count('weitere') == 2
    assert '/students unassign' in message  # The fix hint survives the truncation
    assert message.rstrip().endswith('`/dev orphans apply:True`')

# endregion


# region run_orphan_cleanup

def test_dry_run_deletes_nothing(logs):
    seed()
    guild = FakeGuild()
    message = run(guild, apply=False)

    assert all(connected(sid) for sid in CHANNEL)
    assert logs == []
    assert 'Vorschau' in message
    assert 'Würde löschen (2)' in message and 'Max Muster' in message
    assert f'Schüler `{NAMELESS}`' in message
    assert 'Nicht gelöscht – Schüler noch auf dem Server (1)' in message and 'Anna Bleibt' in message
    assert 'Fritz' not in message


def test_apply_deletes_only_departed_students(logs):
    seed()
    guild = FakeGuild()
    message = run(guild, apply=True)

    assert not connected(GONE) and not connected(NAMELESS)
    assert User(GUILD, GONE).real_name is None  # users row purged as well
    assert connected(STAYING)  # Still a member: never deleted
    assert connected(FINE)
    assert Teacher(GUILD, TEACHER).is_teacher
    assert guild.lock_held_during_fetch is True
    assert 'Gelöscht (2)' in message and 'Max Muster' in message
    assert 'Anna Bleibt' in message and 'Würde' not in message
    [(log_message, details)] = logs
    assert 'bereinigt' in log_message
    assert details['Gelöscht'].startswith('2 Schüler: Max Muster (20)')
    assert details['Ausgeführt von'] == 'dev (1)'


def test_apply_twice_is_harmless(logs):
    seed()
    run(FakeGuild(), apply=True)
    message = run(FakeGuild(), apply=True)
    assert 'Gelöscht' not in message
    assert connected(STAYING) and connected(FINE)


def test_departed_teacher_with_students_is_not_deleted(logs):
    seed()
    Teacher(guild_id=GUILD, id=GONE).save()  # The departed student is also a teacher
    other = Student(guild_id=GUILD, id=50)
    other.save()
    TeacherStudentConnection(guild_id=GUILD, teacher_id=GONE, student_id=50, channel_id=CHANNEL[FINE] + 1).save()
    guild = FakeGuild(channel_ids=(CHANNEL[FINE], CHANNEL[FINE] + 1))

    message = run(guild, apply=True)

    assert connected(GONE)  # GONE is also a teacher with a student
    assert 'Fehlgeschlagen (1)' in message and 'ist Lehrer mit 1 Schüler(n)' in message


def test_unclear_membership_aborts_without_deleting(logs):
    seed()
    guild = FakeGuild()
    guild.fetch_member_error = discord.Forbidden(SimpleNamespace(status=403, reason='Forbidden'), 'nope')
    with pytest.raises(discord.Forbidden):
        run(guild, apply=True)
    assert all(connected(sid) for sid in CHANNEL)


def test_no_channels_from_discord_aborts(logs):
    seed()
    with pytest.raises(CodeError):
        run(FakeGuild(channel_ids=()), apply=True)
    assert all(connected(sid) for sid in CHANNEL)


def test_failed_log_still_reports_deletion(logs, monkeypatch):
    seed()

    async def broken_log(guild, message, details={}):
        raise CodeError('logs not found')

    monkeypatch.setattr(orphans, 'log', broken_log)
    message = run(FakeGuild(), apply=True)
    assert 'Gelöscht (2)' in message and 'Log-Eintrag fehlgeschlagen' in message

# endregion


# region /dev orphans command

class FakeInteraction:
    def __init__(self, guild):
        self.guild = guild
        self.user = ACTOR
        self.calls = []
        self.response = SimpleNamespace(defer=self._defer)
        self.followup = SimpleNamespace(send=self._send)

    async def _defer(self, **kwargs):
        self.calls.append(('defer', kwargs))

    async def _send(self, content, **kwargs):
        self.calls.append(('send', content, kwargs))


def test_dev_orphans_command_defers_ephemeral(logs):
    from cmds.DevGroup import DevGroup

    seed()
    interaction = FakeInteraction(FakeGuild())
    asyncio.run(DevGroup.orphans.callback(DevGroup(), interaction))  # apply defaults to False

    (_, defer_kwargs), (_, content, send_kwargs) = interaction.calls
    assert defer_kwargs['ephemeral'] is True and send_kwargs['ephemeral'] is True
    assert 'Würde löschen (2)' in content
    assert connected(GONE)

# endregion
