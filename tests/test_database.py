import pytest

from Utils.database import (
    DatabaseManager, Teacher, Student, TeacherCalendar, TeacherSettings, TeacherStudentConnection,
)

GUILD = 1


@pytest.fixture(autouse=True)
def db(tmp_path, monkeypatch):
    path = str(tmp_path / 'test.db')
    monkeypatch.setattr(DatabaseManager, '_DatabaseManager__get_db_path',
                        staticmethod(lambda guild_id: path))
    DatabaseManager.create_tables(GUILD)


def make_teacher(tid):
    t = Teacher(guild_id=GUILD, id=tid)
    t.save()
    return t


def test_round_trip_and_edit():
    make_teacher(10)
    cal = TeacherCalendar(guild_id=GUILD, teacher_id=10)
    assert not cal.is_linked and not cal.is_ready
    cal.link('tok')
    assert cal.is_linked and not cal.is_ready
    cal.edit(calendar_id='cid', calendar_name='Cal')
    assert cal.is_ready
    cal.edit(last_prepared_date='2026-10-05')
    loaded = TeacherCalendar(guild_id=GUILD, teacher_id=10)
    assert (loaded.token_cache, loaded.calendar_id, loaded.calendar_name,
            loaded.last_prepared_date) == ('tok', 'cid', 'Cal', '2026-10-05')


def test_delete_and_missing_delete():
    make_teacher(10)
    cal = TeacherCalendar(guild_id=GUILD, teacher_id=10)
    cal.delete()  # missing row: no error
    cal.link('tok')
    cal.delete()
    assert TeacherCalendar.get_all(GUILD) == []


def test_get_all():
    for tid in (10, 11):
        make_teacher(tid)
        TeacherCalendar(guild_id=GUILD, teacher_id=tid).link(f't{tid}')
    assert sorted(c.teacher_id for c in TeacherCalendar.get_all(GUILD)) == [10, 11]


def test_teacher_pop_removes_calendar():
    t = make_teacher(10)
    TeacherCalendar(guild_id=GUILD, teacher_id=10).link('tok')
    t.pop()
    assert TeacherCalendar.get_all(GUILD) == []


def test_find_all_by_teacher_and_channel():
    make_teacher(10)
    for sid, cid in ((20, 100), (21, 101)):
        Student(guild_id=GUILD, id=sid).save()
        TeacherStudentConnection(guild_id=GUILD, teacher_id=10, student_id=sid, channel_id=cid).save()
    conns = TeacherStudentConnection.find_all_by_teacher(GUILD, 10)
    assert sorted(c.student_id for c in conns) == [20, 21]
    assert TeacherStudentConnection.find_all_by_teacher(GUILD, 99) == []
    c = TeacherStudentConnection.find_by_channel(GUILD, 101)
    assert (c.teacher_id, c.student_id) == (10, 21)
    assert TeacherStudentConnection.find_by_channel(GUILD, 555) is None


def test_edit_never_resurrects_and_keeps_other_columns():
    make_teacher(10)
    stale = TeacherCalendar(guild_id=GUILD, teacher_id=10)
    stale.link('tok')
    fresh = TeacherCalendar(guild_id=GUILD, teacher_id=10)
    fresh.edit(calendar_id='cid', calendar_name='Cal')
    stale.edit(token_cache='rotated')  # stale snapshot must not wipe calendar_id
    loaded = TeacherCalendar(guild_id=GUILD, teacher_id=10)
    assert (loaded.token_cache, loaded.calendar_id) == ('rotated', 'cid')

    fresh.delete()
    stale.edit(last_prepared_date='2026-10-05')  # e.g. a prep finishing after disconnect
    assert TeacherCalendar.get_all(GUILD) == []


def test_get_all_teacher_ids_only_with_category():
    for tid, category in ((10, 500), (11, None), (12, 501)):
        t = Teacher(guild_id=GUILD, id=tid)
        t.teaching_category = category
        t.save()
    assert sorted(DatabaseManager.get_all_teacher_ids(GUILD)) == [10, 12]


def test_teacher_settings_default_without_row():
    make_teacher(10)
    assert TeacherSettings(guild_id=GUILD, teacher_id=10).daily_summary is True
    assert TeacherSettings(guild_id=GUILD, teacher_id=99).daily_summary is True  # unknown teacher


def test_teacher_settings_set_and_persist():
    make_teacher(10)
    settings = TeacherSettings(guild_id=GUILD, teacher_id=10)
    settings.set_daily_summary(False)
    assert settings.daily_summary is False
    assert TeacherSettings(guild_id=GUILD, teacher_id=10).daily_summary is False
    settings.set_daily_summary(True)
    assert TeacherSettings(guild_id=GUILD, teacher_id=10).daily_summary is True


def test_teacher_settings_survive_calendar_disconnect():
    make_teacher(10)
    cal = TeacherCalendar(guild_id=GUILD, teacher_id=10)
    cal.link('tok')
    TeacherSettings(guild_id=GUILD, teacher_id=10).set_daily_summary(False)
    cal.delete()
    assert TeacherSettings(guild_id=GUILD, teacher_id=10).daily_summary is False


def test_teacher_pop_removes_settings():
    t = make_teacher(10)
    TeacherSettings(guild_id=GUILD, teacher_id=10).set_daily_summary(False)
    t.pop()  # must not fail on the foreign key
    make_teacher(10)
    assert TeacherSettings(guild_id=GUILD, teacher_id=10).daily_summary is True
