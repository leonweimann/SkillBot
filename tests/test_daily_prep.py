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
    lounge = SimpleNamespace(name='lounge', members=[])
    guild = SimpleNamespace(id=5, categories=[teacher_category, archive_category], text_channels=[anna, bert],
                            voice_channels=[lounge])

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

    logs = []

    async def fake_log(guild, message, details={}):
        logs.append(message)

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
    monkeypatch.setattr(daily_prep.Subuser, 'get_user_of_subuser', lambda g, m: None)

    return SimpleNamespace(guild=guild, anna=anna, bert=bert, db_cal=db_cal, sorted=sorted_categories,
                           connections=connections, lounge=lounge, logs=logs)

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


# region stash_all

def test_stash_all_archives_only_teacher_category_and_never_pops(env):
    cmd = FakeChannel(13, 'cmd', TEACHER_CATEGORY_ID)
    foreign = FakeChannel(14, 'fremder-channel', TEACHER_CATEGORY_ID)
    env.guild.text_channels.extend([cmd, foreign])

    result = asyncio.run(daily_prep.stash_all(env.guild, TEACHER_ID))

    assert result.stashed == ['bert-mueller']
    assert result.popped == [] and result.failed == [] and result.missing == []
    assert env.bert.edits[0]['category'].id == ARCHIVE_CATEGORY_ID
    assert env.anna.edits == []  # archived student with no calendar is never popped
    assert cmd.edits == [] and foreign.edits == []
    assert sorted(env.sorted) == [TEACHER_CATEGORY_ID, ARCHIVE_CATEGORY_ID]
    assert env.db_cal.edits == []  # calendar data untouched


def test_stash_all_does_not_fetch_calendar(env, monkeypatch):
    async def failing_get_events(cal, start, end):
        raise AssertionError('calendar must not be fetched')

    monkeypatch.setattr(msgraph, 'get_events', failing_get_events)
    result = asyncio.run(daily_prep.stash_all(env.guild, TEACHER_ID))
    assert result.stashed == ['bert-mueller']


def test_stash_all_collects_failures_without_logging(env, monkeypatch):
    logged = []

    async def recording_log(guild, message, details={}):
        logged.append(message)

    async def failing_edit(**kwargs):
        raise RuntimeError('kaputt')

    monkeypatch.setattr(daily_prep, 'log', recording_log)
    env.bert.edit = failing_edit

    result = asyncio.run(daily_prep.stash_all(env.guild, TEACHER_ID))

    assert result.failed == ['bert-mueller']
    assert result.stashed == []
    assert logged == []  # the caller writes the single log entry


def test_stash_all_nothing_to_do(env):
    env.bert.category_id = ARCHIVE_CATEGORY_ID

    result = asyncio.run(daily_prep.stash_all(env.guild, TEACHER_ID))

    assert result.stashed == [] and result.popped == []
    assert env.sorted == []


def test_stash_all_missing_teacher_category_raises_code_error(env):
    env.guild.categories = []
    with pytest.raises(daily_prep.CodeError):
        asyncio.run(daily_prep.stash_all(env.guild, TEACHER_ID))


def test_format_stash_details():
    result = PrepResult(plan=DayPlan(), stashed=['bert-mueller', 'a`b'], failed=['carl'])
    details = daily_prep.format_stash_details(TEACHER_ID, result)
    assert details == {
        'Lehrer': f'<@{TEACHER_ID}>',
        'Archiviert': "2: bert-mueller, a'b",
        'Fehlgeschlagen': '1: carl',
    }

# endregion


# region DailyPreparation cog

CALENDAR_TEACHER = 31
PLAIN_TEACHER = 32      # teacher row, no calendar row
LINKED_TEACHER = 33     # linked account, but no calendar selected


@pytest.fixture
def cog_env(monkeypatch):
    from cogs import DailyPreparation as cog_module

    calendars = {
        CALENDAR_TEACHER: FakeDbCal(ready=True),
        PLAIN_TEACHER: FakeDbCal(ready=False),
        LINKED_TEACHER: FakeDbCal(ready=False),
    }
    for cal in calendars.values():
        cal.last_prepared_date = None
    calls = []
    logged = []
    stash_results = {}

    async def fake_prepare(guild, teacher_id, day, dry_run=False):
        calls.append(('prepare', teacher_id))
        return PrepResult(plan=DayPlan())

    async def fake_stash_all(guild, teacher_id):
        calls.append(('stash', teacher_id))
        return stash_results.get(teacher_id, PrepResult(plan=DayPlan()))

    async def fake_log(guild, message, details={}):
        logged.append((message, details))

    members = {CALENDAR_TEACHER, PLAIN_TEACHER, LINKED_TEACHER}
    guild = SimpleNamespace(id=5, name='Server', get_member=lambda uid: object() if uid in members else None)

    monkeypatch.setattr(cog_module, 'DatabaseManager',
                        SimpleNamespace(get_all_teacher_ids=lambda g: list(calendars)))
    monkeypatch.setattr(cog_module, 'TeacherCalendar', lambda g, t: calendars[t])
    monkeypatch.setattr(cog_module, 'prepare_teacher', fake_prepare)
    monkeypatch.setattr(cog_module, 'stash_all', fake_stash_all)
    monkeypatch.setattr(cog_module, 'get_cmd_channel', lambda g, t: None)
    monkeypatch.setattr(cog_module, 'log', fake_log)
    monkeypatch.setattr(msgraph, 'is_configured', lambda: True)

    cog = cog_module.DailyPreparation(SimpleNamespace(guilds=[guild]))
    return SimpleNamespace(cog=cog, calls=calls, logged=logged, calendars=calendars, members=members,
                           stash_results=stash_results, guild=guild)


def test_nightly_dispatches_calendar_teachers_to_prepare_and_others_to_stash_all(cog_env):
    asyncio.run(cog_env.cog._run_all(catch_up=False))
    assert sorted(cog_env.calls) == [
        ('prepare', CALENDAR_TEACHER), ('stash', PLAIN_TEACHER), ('stash', LINKED_TEACHER)
    ]


def test_catch_up_never_stashes(cog_env):
    asyncio.run(cog_env.cog._run_all(catch_up=True))
    assert cog_env.calls == [('prepare', CALENDAR_TEACHER)]


def test_catch_up_skips_teachers_prepared_today(cog_env, monkeypatch):
    from cogs import DailyPreparation as cog_module

    class FakeDateTime:
        @staticmethod
        def now(tz=None):
            return daily_prep.datetime(2026, 10, 5, 9, 0, tzinfo=tz)

    monkeypatch.setattr(cog_module, 'datetime', FakeDateTime)
    cog_env.calendars[CALENDAR_TEACHER].last_prepared_date = '2026-10-05'
    asyncio.run(cog_env.cog._run_all(catch_up=True))
    assert cog_env.calls == []


def test_graph_not_configured_stashes_everyone(cog_env, monkeypatch):
    monkeypatch.setattr(msgraph, 'is_configured', lambda: False)
    asyncio.run(cog_env.cog._run_all(catch_up=False))
    assert sorted(cog_env.calls) == [
        ('stash', CALENDAR_TEACHER), ('stash', PLAIN_TEACHER), ('stash', LINKED_TEACHER)
    ]


def test_graph_not_configured_catch_up_does_nothing(cog_env, monkeypatch):
    monkeypatch.setattr(msgraph, 'is_configured', lambda: False)
    asyncio.run(cog_env.cog._run_all(catch_up=True))
    assert cog_env.calls == []


def test_stash_all_logs_once_only_when_something_happened(cog_env):
    cog_env.stash_results[PLAIN_TEACHER] = PrepResult(plan=DayPlan(), stashed=['bert-mueller'], failed=['carl'])

    asyncio.run(cog_env.cog._run_all(catch_up=False))

    stash_logs = [details for message, details in cog_env.logged if 'Archivieren' in message]
    assert stash_logs == [{
        'Lehrer': f'<@{PLAIN_TEACHER}>',
        'Archiviert': '1: bert-mueller',
        'Fehlgeschlagen': '1: carl',
    }]


def test_non_member_teacher_is_skipped_and_logged_once(cog_env):
    cog_env.members.discard(PLAIN_TEACHER)

    asyncio.run(cog_env.cog._run_all(catch_up=False))
    asyncio.run(cog_env.cog._run_all(catch_up=False))

    assert ('stash', PLAIN_TEACHER) not in cog_env.calls
    skipped = [m for m, d in cog_env.logged if 'übersprungen' in m]
    assert len(skipped) == 1


def test_stash_all_error_is_reported_once_per_day(cog_env, monkeypatch):
    from cogs import DailyPreparation as cog_module

    async def failing_stash_all(guild, teacher_id):
        raise daily_prep.CodeError('Lehrer hat keine Kategorie')

    monkeypatch.setattr(cog_module, 'stash_all', failing_stash_all)

    asyncio.run(cog_env.cog._run_all(catch_up=False))
    asyncio.run(cog_env.cog._run_all(catch_up=False))

    errors = [d['Lehrer'] for m, d in cog_env.logged if 'fehlgeschlagen' in m]
    assert sorted(errors) == [f'<@{PLAIN_TEACHER}>', f'<@{LINKED_TEACHER}>']

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


# region lounge

def test_stash_all_keeps_students_waiting_in_lounge(env):
    env.lounge.members.append(SimpleNamespace(id=22, bot=False))  # bert waits in the lounge

    result = asyncio.run(daily_prep.stash_all(env.guild, TEACHER_ID))

    assert result.stashed == []
    assert env.bert.edits == []


def test_lounge_sub_account_keeps_main_student(env, monkeypatch):
    monkeypatch.setattr(daily_prep.Subuser, 'get_user_of_subuser',
                        lambda g, m: SimpleNamespace(id=22) if m == 99 else None)
    env.lounge.members.append(SimpleNamespace(id=99, bot=False))  # bert's second account

    result = asyncio.run(daily_prep.stash_all(env.guild, TEACHER_ID))

    assert result.stashed == []


def test_prepare_teacher_pops_student_waiting_in_lounge(env):
    env.lounge.members.append(SimpleNamespace(id=22, bot=False))  # no appointment, but waiting

    result = asyncio.run(daily_prep.prepare_teacher(env.guild, TEACHER_ID, DAY))

    assert result.popped == ['anna-meier']
    assert result.stashed == []  # bert stays in the teacher category


def test_students_in_lounge_ignores_bots_and_missing_lounge(env):
    env.lounge.members.extend([SimpleNamespace(id=21, bot=False), SimpleNamespace(id=1, bot=True)])
    assert daily_prep.students_in_lounge(env.guild) == {21}
    env.guild.voice_channels = []
    assert daily_prep.students_in_lounge(env.guild) == set()

# endregion
