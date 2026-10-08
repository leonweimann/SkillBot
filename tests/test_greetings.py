"""Offline tests for cogs.Greetings.on_member_remove (temp database, Discord fakes)."""

import asyncio
from types import SimpleNamespace

import discord
import pytest

from cogs import Greetings as greetings
from cogs.Greetings import Greetings
from Utils.database import (
    DatabaseManager, Student, Subuser, Teacher, TeacherStudentConnection, User,
)

GUILD = 1
TEACHER, STUDENT, SUB_ACCOUNT, CHANNEL = 10, 20, 30, 100


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

    monkeypatch.setattr(greetings, 'log', fake_log)
    return entries


class FakeChannel:
    def __init__(self, id, fail=False):
        self.id = id
        self.fail = fail
        self.deleted = False

    async def delete(self):
        if self.fail:
            raise discord.Forbidden(SimpleNamespace(status=403, reason='Forbidden'), 'Missing Permissions')
        self.deleted = True


def make_member(id, channels=()):
    by_id = {c.id: c for c in channels}
    guild = SimpleNamespace(id=GUILD, get_channel=by_id.get)
    return SimpleNamespace(id=id, name=f'user{id}', display_name=f'User {id}', guild=guild)


def seed_student():
    Teacher(guild_id=GUILD, id=TEACHER).save()
    student = Student(guild_id=GUILD, id=STUDENT)
    student.real_name = 'Max Muster'
    student.save()
    TeacherStudentConnection(guild_id=GUILD, teacher_id=TEACHER, student_id=STUDENT, channel_id=CHANNEL).save()
    Subuser(guild_id=GUILD, id=STUDENT, subuser_id=SUB_ACCOUNT).save()


def remove(member):
    asyncio.run(Greetings(None).on_member_remove(member))


def test_leaving_student_is_fully_removed(logs):
    seed_student()
    channel = FakeChannel(CHANNEL)
    remove(make_member(STUDENT, [channel]))

    assert channel.deleted
    assert TeacherStudentConnection.find_by_student(GUILD, STUDENT) is None
    assert not User(GUILD, STUDENT).is_student
    assert User(GUILD, STUDENT).real_name is None  # users row is gone
    assert Subuser.get_all_subusers(GUILD, STUDENT) == []
    assert Teacher(GUILD, TEACHER).is_teacher
    [(message, details)] = logs
    assert message == 'Removed User 20 from database'
    assert details['User type'] == 'Student'
    assert 'teacher_student=1' in details['Deleted rows'] and 'users=1' in details['Deleted rows']
    assert details['Channels'] == f'{CHANNEL} deleted'


def test_missing_channel_still_purges(logs):
    seed_student()
    remove(make_member(STUDENT))  # Channel already gone
    assert TeacherStudentConnection.find_by_student(GUILD, STUDENT) is None
    assert logs[0][1]['Channels'] == f'{CHANNEL} not found'


def test_failed_channel_delete_still_purges(logs):
    seed_student()
    remove(make_member(STUDENT, [FakeChannel(CHANNEL, fail=True)]))
    assert TeacherStudentConnection.find_by_student(GUILD, STUDENT) is None
    assert 'not deleted' in logs[0][1]['Channels']


def test_teacher_with_students_is_kept(logs):
    seed_student()
    remove(make_member(TEACHER))
    assert Teacher(GUILD, TEACHER).is_teacher
    assert TeacherStudentConnection.find_by_student(GUILD, STUDENT) is not None
    [(message, details)] = logs
    assert message.startswith('Kept User 10 in database')
    assert details['Students'] == str(STUDENT)


def test_unknown_member_leaving(logs):
    remove(make_member(99))
    [(message, _)] = logs
    assert message == 'User 99 left (no database entries)'
