"""Offline tests for Coordination.daily_prep (no Discord, no Graph, no database)."""

import asyncio
from datetime import date
from types import SimpleNamespace

import pytest

from Coordination import daily_prep
from Coordination.daily_prep import PrepResult, format_summary
from Coordination.schedule import DayPlan
from Utils import msgraph


TEACHER_ID = 1
TEACHER_CATEGORY_ID = 100
ARCHIVE_CATEGORY_ID = 200
DAY = date(2026, 10, 5)


# region Fakes

class FakeChannel:
    def __init__(self, id, name, category_id):
        self.id = id
        self.name = name
        self.category_id = category_id
        self.edits = []

    @property
    def mention(self):
        return f'<#{self.id}>'

    async def edit(self, **kwargs):
        self.edits.append(kwargs)


class FakeDbCal:
    def __init__(self, ready=True):
        self.is_ready = ready
        self.calendar_id = 'cal'
        self.token_cache = 'cache'
        self.edits = []

    def edit(self, **kwargs):
        self.edits.append(kwargs)


@pytest.fixture
def env(monkeypatch):
    teacher_category = SimpleNamespace(id=TEACHER_CATEGORY_ID, name='Lehrer')
    archive_category = SimpleNamespace(id=ARCHIVE_CATEGORY_ID, name='Archiv')
    # anna has an appointment but is archived, bert has none but is in the teacher category
    anna = FakeChannel(11, 'anna-meier', ARCHIVE_CATEGORY_ID)
    bert = FakeChannel(12, 'bert-mueller', TEACHER_CATEGORY_ID)
    guild = SimpleNamespace(id=5, categories=[teacher_category, archive_category], text_channels=[anna, bert])

    db_cal = FakeDbCal()
    sorted_categories = []
    events = [{'subject': 'Mathematik mit Anna Meier'}]

    async def fake_get_events(cal, start, end):
        return events

    class FakeArchiveCategory:
        def __init__(self):
            self.category = archive_category

        @classmethod
        async def make(cls, guild):
            return cls()

        async def add_channel(self, channel):
            await channel.edit(category=self.category)
            return self.category

    class FakeSorter:
        async def sort_channels_in_category(self, category):
            sorted_categories.append(category.id)

    async def fake_log(*args, **kwargs):
        pass

    connections = [
        SimpleNamespace(student_id=21, channel_id=11, teacher_id=TEACHER_ID),
        SimpleNamespace(student_id=22, channel_id=12, teacher_id=TEACHER_ID),
    ]
    names = {21: 'Anna Meier', 22: 'Bert Müller'}

    monkeypatch.setattr(daily_prep, 'TeacherCalendar', lambda g, t: db_cal)
    monkeypatch.setattr(daily_prep, 'Teacher', lambda g, t: SimpleNamespace(teaching_category=TEACHER_CATEGORY_ID))
    monkeypatch.setattr(daily_prep, 'Student', lambda g, s: SimpleNamespace(real_name=names[s]))
    monkeypatch.setattr(daily_prep, 'TeacherStudentConnection',
                        SimpleNamespace(find_all_by_teacher=lambda g, t: connections))
    monkeypatch.setattr(daily_prep, 'Archive',
                        SimpleNamespace(get_all=lambda g: [SimpleNamespace(id=ARCHIVE_CATEGORY_ID)]))
    monkeypatch.setattr(daily_prep, 'ArchiveCategory', FakeArchiveCategory)
    monkeypatch.setattr(daily_prep, 'channel_sorting_coordinator', FakeSorter())
    monkeypatch.setattr(daily_prep, 'log', fake_log)
    monkeypatch.setattr(msgraph, 'get_events', fake_get_events)

    return SimpleNamespace(guild=guild, anna=anna, bert=bert, db_cal=db_cal, sorted=sorted_categories,
                           connections=connections)

# endregion


# region prepare_teacher

def test_graph_error_moves_nothing(env, monkeypatch):
    async def failing_get_events(cal, start, end):
        raise msgraph.GraphAuthError('expired')

    monkeypatch.setattr(msgraph, 'get_events', failing_get_events)

    with pytest.raises(msgraph.GraphAuthError):
        asyncio.run(daily_prep.prepare_teacher(env.guild, TEACHER_ID, DAY))

    assert env.anna.edits == [] and env.bert.edits == []
    assert env.db_cal.edits == []
    assert env.sorted == []


def test_dry_run_moves_nothing(env):
    result = asyncio.run(daily_prep.prepare_teacher(env.guild, TEACHER_ID, DAY, dry_run=True))

    assert result.popped == ['anna-meier']
    assert result.stashed == ['bert-mueller']
    assert env.anna.edits == [] and env.bert.edits == []
    assert env.db_cal.edits == []
    assert env.sorted == []


def test_real_run_moves_and_sorts(env):
    result = asyncio.run(daily_prep.prepare_teacher(env.guild, TEACHER_ID, DAY))

    assert result.popped == ['anna-meier']
    assert result.stashed == ['bert-mueller']
    assert env.anna.edits[0]['category'].id == TEACHER_CATEGORY_ID
    assert 'sync_permissions' not in env.anna.edits[0]
    assert env.bert.edits[0]['category'].id == ARCHIVE_CATEGORY_ID
    assert sorted(env.sorted) == [TEACHER_CATEGORY_ID, ARCHIVE_CATEGORY_ID]
    assert env.db_cal.edits == [{'last_prepared_date': '2026-10-05'}]


def test_missing_channel_is_skipped(env):
    env.guild.text_channels.remove(env.anna)

    result = asyncio.run(daily_prep.prepare_teacher(env.guild, TEACHER_ID, DAY))

    assert result.missing == ['Anna Meier']
    assert result.popped == []
    assert result.stashed == ['bert-mueller']


def test_calendar_not_ready_raises_usage_error(env):
    env.db_cal.is_ready = False
    with pytest.raises(daily_prep.UsageError):
        asyncio.run(daily_prep.prepare_teacher(env.guild, TEACHER_ID, DAY))


def test_missing_teacher_category_raises_code_error(env):
    env.guild.categories = []
    with pytest.raises(daily_prep.CodeError):
        asyncio.run(daily_prep.prepare_teacher(env.guild, TEACHER_ID, DAY))

# endregion


# region pop_to_teacher

def test_pop_archived_channel(env, monkeypatch):
    async def fetch_channel(channel_id):
        return env.anna

    env.guild.fetch_channel = fetch_channel
    # The fake is not a discord.TextChannel, so patch the type check target
    monkeypatch.setattr(daily_prep.discord, 'TextChannel', FakeChannel)

    assert asyncio.run(daily_prep.pop_to_teacher(env.guild, env.connections[0])) is True
    assert env.anna.edits[0]['category'].id == TEACHER_CATEGORY_ID
    assert env.sorted == [TEACHER_CATEGORY_ID]


def test_pop_not_archived_channel(env, monkeypatch):
    async def fetch_channel(channel_id):
        return env.bert

    env.guild.fetch_channel = fetch_channel
    monkeypatch.setattr(daily_prep.discord, 'TextChannel', FakeChannel)

    assert asyncio.run(daily_prep.pop_to_teacher(env.guild, env.connections[1])) is False
    assert env.bert.edits == []


def test_is_archived_category(env):
    assert daily_prep.is_archived_category(env.guild, ARCHIVE_CATEGORY_ID)
    assert not daily_prep.is_archived_category(env.guild, TEACHER_CATEGORY_ID)
    assert not daily_prep.is_archived_category(env.guild, None)

# endregion


# region format_summary

def make_result(**kwargs) -> PrepResult:
    plan = DayPlan(
        student_ids={21},
        matched={21: 'Mathematik mit Anna Meier'},
        skipped=[('Teams Call', 'online-meeting'), ('Telefonat', 'telefon')],
        unmatched=['Deutsch mit Unbekannt Person'],
        ambiguous=['Englisch mit Max'],
    )
    return PrepResult(plan=plan, **kwargs)


def test_summary_real_run():
    text = format_summary(make_result(popped=['anna-meier'], stashed=['bert-mueller']), dry_run=False)
    assert 'Tagesvorbereitung abgeschlossen' in text
    assert 'Hereingeholt (1): `anna-meier`' in text
    assert 'Archiviert (1): `bert-mueller`' in text
    assert 'Deutsch mit Unbekannt Person' in text
    assert 'Englisch mit Max' in text
    assert 'nichts verschoben' not in text


def test_summary_dry_run_says_nothing_moved():
    text = format_summary(make_result(popped=['anna-meier'], stashed=['bert-mueller']), dry_run=True)
    assert 'nichts verschoben' in text
    assert 'Würde hereinholen (1)' in text
    assert 'Würde archivieren (1)' in text
    assert 'Hereingeholt' not in text


def test_summary_without_moves():
    text = format_summary(make_result(), dry_run=False)
    assert 'Keine Channel-Verschiebungen nötig' in text


def test_summary_truncates_long_lists():
    many = [f'schueler-mit-sehr-langem-namen-{i:03d}' for i in range(300)]
    result = make_result(popped=many, stashed=many, missing=many, failed=many)
    result.plan.unmatched = [f'Mathematik mit Person {i}' for i in range(300)]
    result.plan.ambiguous = [f'Physik mit Person {i}' for i in range(300)]

    text = format_summary(result, dry_run=False)
    assert len(text) < 2000
    assert 'weitere' in text
    assert 'Hereingeholt (300)' in text

# endregion
