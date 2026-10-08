import pytest

from Utils.database import (
    DatabaseError, DatabaseManager, DevMode, Student, Subuser, Teacher, TeacherCalendar,
    TeacherHasStudentsError, TeacherSettings, TeacherStudentConnection, User, UserVoiceChannelJoin,
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


# region purge_user

def count_rows(table, column, value):
    with DatabaseManager._connect(GUILD) as conn:
        return conn.execute(f'SELECT COUNT(*) FROM {table} WHERE {column} = ?', (value,)).fetchone()[0]


def make_student(sid, tid=10, cid=100):
    s = Student(guild_id=GUILD, id=sid)
    s.real_name = f'Schüler {sid}'
    s.save()
    TeacherStudentConnection(guild_id=GUILD, teacher_id=tid, student_id=sid, channel_id=cid).save()
    return s


def test_purge_student_removes_everything():
    make_teacher(10)
    make_student(20)
    Subuser(guild_id=GUILD, id=20, subuser_id=30).save()
    UserVoiceChannelJoin(guild_id=GUILD, user_id=20, voice_channel_id=5, join_time='2026-10-08 10:00:00').save()
    DevMode.set_dev_mode(GUILD, 20, True)

    deleted = DatabaseManager.purge_user(GUILD, 20)

    assert deleted['teacher_student'] == 1
    assert deleted['students'] == 1
    assert deleted['subusers'] == 1
    assert deleted['user_voice_channel_join'] == 1
    assert deleted['dev_mode'] == 1
    assert deleted['users'] == 1
    assert deleted['teachers'] == 0
    for table, column in (('users', 'id'), ('students', 'user_id'), ('teacher_student', 'student_id'),
                          ('subusers', 'user_id'), ('user_voice_channel_join', 'user_id'), ('dev_mode', 'user_id')):
        assert count_rows(table, column, 20) == 0
    assert Teacher(guild_id=GUILD, id=10).is_teacher  # The teacher is untouched


def test_purge_removes_sub_account_relation():
    make_teacher(10)
    make_student(20)
    Subuser(guild_id=GUILD, id=20, subuser_id=30).save()
    deleted = DatabaseManager.purge_user(GUILD, 30)  # The sub account leaves
    assert deleted['subusers'] == 1
    assert Subuser.get_all_subusers(GUILD, 20) == []
    assert Student(guild_id=GUILD, id=20).is_student


def test_purge_unknown_user_deletes_nothing():
    assert sum(DatabaseManager.purge_user(GUILD, 99).values()) == 0


def test_purge_teacher_without_students_removes_calendar_and_settings():
    make_teacher(10)
    TeacherCalendar(guild_id=GUILD, teacher_id=10).link('tok')
    TeacherSettings(guild_id=GUILD, teacher_id=10).set_daily_summary(False)
    deleted = DatabaseManager.purge_user(GUILD, 10)
    assert (deleted['teacher_calendar'], deleted['teacher_settings'], deleted['teachers'], deleted['users']) == (1, 1, 1, 1)
    assert TeacherCalendar.get_all(GUILD) == []


def test_purge_teacher_with_students_is_refused():
    make_teacher(10)
    TeacherCalendar(guild_id=GUILD, teacher_id=10).link('tok')
    make_student(20)
    with pytest.raises(TeacherHasStudentsError) as info:
        DatabaseManager.purge_user(GUILD, 10)
    assert info.value.student_count == 1
    assert count_rows('teachers', 'user_id', 10) == 1
    assert count_rows('users', 'id', 10) == 1
    assert len(TeacherCalendar.get_all(GUILD)) == 1
    assert TeacherStudentConnection.find_by_student(GUILD, 20) is not None


def test_purge_rolls_back_on_error():
    make_teacher(10)
    make_student(20)
    Subuser(guild_id=GUILD, id=20, subuser_id=30).save()
    with DatabaseManager._connect(GUILD) as conn:  # The last statement fails
        conn.execute("CREATE TRIGGER fail_user_delete BEFORE DELETE ON users "
                     "BEGIN SELECT RAISE(ABORT, 'boom'); END")
    with pytest.raises(DatabaseError, match='boom'):
        DatabaseManager.purge_user(GUILD, 20)
    assert count_rows('users', 'id', 20) == 1
    assert count_rows('students', 'user_id', 20) == 1
    assert count_rows('teacher_student', 'student_id', 20) == 1
    assert count_rows('subusers', 'user_id', 20) == 1


def test_plain_user_delete_fails_on_foreign_keys():
    """Documents why `purge_user` exists: `User.delete` alone violates the foreign keys."""
    make_teacher(10)
    make_student(20)
    with pytest.raises(DatabaseError):
        User(guild_id=GUILD, id=20).delete()


def test_get_all_connections():
    make_teacher(10)
    make_student(20, cid=100)
    make_student(21, cid=101)
    assert sorted((c.student_id, c.channel_id) for c in TeacherStudentConnection.get_all(GUILD)) == [(20, 100), (21, 101)]

# endregion
