import pytest

from Coordination.schedule import (
    CalendarEvent, DayPlan, compute_moves, extract_student_name, match_name,
    normalize_name, plan_day, skip_reason,
)


# region from_graph

def test_from_graph_full():
    event = CalendarEvent.from_graph({
        'subject': 'Mathematik mit Laura Schieweck', 'isAllDay': True, 'isCancelled': True,
        'isOnlineMeeting': True, 'location': {'displayName': 'Discord'}, 'categories': ['Telefon', 'Rot'],
    })
    assert event == CalendarEvent('Mathematik mit Laura Schieweck', True, True, True, 'Discord', ('Telefon', 'Rot'))


@pytest.mark.parametrize('data', [{}, None, {'subject': None, 'location': None, 'categories': None, 'isAllDay': None}])
def test_from_graph_tolerates_missing_and_none(data):
    event = CalendarEvent.from_graph(data)
    assert event == CalendarEvent('')


def test_from_graph_partial():
    event = CalendarEvent.from_graph({'subject': 'Nägel', 'location': {}, 'isOnlineMeeting': True})
    assert event.subject == 'Nägel'
    assert event.location == ''
    assert event.is_online_meeting and not event.is_all_day

# endregion


# region skip_reason

def test_skip_reason_none_for_normal_event():
    assert skip_reason(CalendarEvent('Mathematik mit Luca Kopf', location='Discord')) is None


def test_skip_reason_each():
    assert skip_reason(CalendarEvent('x', is_cancelled=True)) == 'abgesagt'
    assert skip_reason(CalendarEvent('x', is_all_day=True)) == 'ganztägig'
    assert skip_reason(CalendarEvent('x', is_online_meeting=True)) == 'online-meeting'
    assert skip_reason(CalendarEvent('x', categories=('Telefon',))) == 'telefon'
    assert skip_reason(CalendarEvent('x', categories=('rot', ' TELEFON '))) == 'telefon'
    assert skip_reason(CalendarEvent('x', location='+49 171 1234567')) == 'telefonnummer'
    assert skip_reason(CalendarEvent('x', location='0171/1234567')) == 'telefonnummer'
    assert skip_reason(CalendarEvent('x', location='(0171) 123-4567')) == 'telefonnummer'


def test_skip_reason_order():
    event = CalendarEvent('x', True, True, True, '0171 1234567', ('Telefon',))
    assert skip_reason(event) == 'abgesagt'
    event = CalendarEvent('x', True, False, True, '0171 1234567', ('Telefon',))
    assert skip_reason(event) == 'ganztägig'
    event = CalendarEvent('x', False, False, True, '0171 1234567', ('Telefon',))
    assert skip_reason(event) == 'online-meeting'
    event = CalendarEvent('x', False, False, False, '0171 1234567', ('Telefon',))
    assert skip_reason(event) == 'telefon'


@pytest.mark.parametrize('location', ['Discord', 'Raum 12', '', 'Raum 123456', '12345', '+49 171'])
def test_location_is_not_phone(location):
    assert skip_reason(CalendarEvent('x', location=location)) is None

# endregion


# region names

def test_extract_student_name():
    assert extract_student_name('Mathematik mit Laura Schieweck') == 'Laura Schieweck'
    assert extract_student_name('Mathematik MIT  Ada   Özyar ') == 'Ada Özyar'
    assert extract_student_name('Physik mit Martin mit Cieslak') == 'Martin mit Cieslak'


@pytest.mark.parametrize('subject', ['Mijatovic', 'Nägel', 'BOK Kurse anmelden', 'Maria Oertner Test', '', 'Mathe mit', 'Mathe mit  ', 'Smith'])
def test_extract_student_name_none(subject):
    assert extract_student_name(subject) is None


def test_normalize_name():
    assert normalize_name('  Ada   ÖZYAR ') == 'ada oezyar'
    assert normalize_name('Strauß-Müller') == 'strauss mueller'
    assert normalize_name('Anna_Maria Bär') == 'anna maria baer'
    assert normalize_name('Ada Özyar') == normalize_name('Ada Oezyar')
    # decomposed umlaut (NFD) is handled via NFKC
    assert normalize_name('Ada Özyar') == 'ada oezyar'

# endregion


# region match_name

STUDENTS = {1: 'Laura Schieweck', 2: 'Ada Oezyar', 3: 'Anna-Lena Müller', 4: 'Martin Cieslak'}


def test_match_exact_case_insensitive():
    assert match_name('laura SCHIEWECK', STUDENTS) == (1, False)


def test_match_umlaut_both_directions():
    assert match_name('Ada Özyar', STUDENTS) == (2, False)
    assert match_name('Anna-Lena Mueller', STUDENTS) == (3, False)
    assert match_name('Ada Oezyar', {9: 'Ada Özyar'}) == (9, False)


def test_match_hyphen_and_space():
    assert match_name('Anna Lena Müller', STUDENTS) == (3, False)


def test_match_token_superset():
    students = {1: 'Laura Marie Schieweck', 2: 'Luca Kopf'}
    assert match_name('Laura Schieweck', students) == (1, False)


def test_match_single_token_never_superset():
    students = {1: 'Laura Marie Schieweck'}
    assert match_name('Laura', students) == (None, False)


def test_match_ambiguous_superset():
    students = {1: 'Laura Marie Schieweck', 2: 'Laura Anna Schieweck'}
    assert match_name('Laura Schieweck', students) == (None, True)


def test_match_ambiguous_exact():
    assert match_name('Luca Kopf', {1: 'Luca Kopf', 2: 'luca kopf'}) == (None, True)


def test_match_exact_wins_over_superset():
    students = {1: 'Laura Schieweck', 2: 'Laura Marie Schieweck'}
    assert match_name('Laura Schieweck', students) == (1, False)


def test_match_unmatched():
    assert match_name('Peter Pan', STUDENTS) == (None, False)
    assert match_name('', STUDENTS) == (None, False)
    assert match_name('Laura Schieweck', {}) == (None, False)

# endregion


# region plan_day

def test_plan_day_aggregate():
    students = {1: 'Laura Schieweck', 2: 'Luca Kopf', 3: 'Ada Oezyar', 4: 'Anna Marie Lang', 5: 'Anna Lena Lang'}
    events = [
        CalendarEvent('Mathematik mit Laura Schieweck'),
        CalendarEvent('Physik mit  laura   schieweck'),  # second appointment, same student
        CalendarEvent('Mathematik mit Ada Özyar', location='Discord'),
        CalendarEvent('Mathematik mit Luca Kopf', is_cancelled=True),
        CalendarEvent('Informatik mit Manfred Suppmann'),  # unknown
        CalendarEvent('Mathematik mit Anna Lang'),  # ambiguous
        CalendarEvent('Mathematik mit Martin Cieslak', is_online_meeting=True),
        CalendarEvent('Mathematik mit Neu Kunde', categories=('Telefon',)),
        CalendarEvent('Mathematik mit Neu Kunde2', location='0171/1234567'),
        CalendarEvent('Urlaub', is_all_day=True),
        CalendarEvent('Mijatovic'),
        CalendarEvent('BOK Kurse anmelden'),
    ]
    plan = plan_day(events, students)

    assert plan.student_ids == {1, 3}
    assert plan.matched == {1: 'Mathematik mit Laura Schieweck', 3: 'Mathematik mit Ada Özyar'}
    assert plan.unmatched == ['Informatik mit Manfred Suppmann']
    assert plan.ambiguous == ['Mathematik mit Anna Lang']
    assert plan.skipped == [
        ('Mathematik mit Luca Kopf', 'abgesagt'),
        ('Mathematik mit Martin Cieslak', 'online-meeting'),
        ('Mathematik mit Neu Kunde', 'telefon'),
        ('Mathematik mit Neu Kunde2', 'telefonnummer'),
        ('Urlaub', 'ganztägig'),
        ('Mijatovic', 'kein-titelmuster'),
        ('BOK Kurse anmelden', 'kein-titelmuster'),
    ]


def test_plan_day_empty():
    plan = plan_day([], {1: 'Laura Schieweck'})
    assert plan == DayPlan(set(), {}, [], [], [])

# endregion


# region compute_moves

TEACHER_CAT = 100
ARCHIVE_CAT = 200


def test_compute_moves():
    connections = [
        (1, 11, ARCHIVE_CAT),   # target, archived -> pop
        (2, 12, TEACHER_CAT),   # target, already there -> untouched
        (3, 13, TEACHER_CAT),   # not target, in teacher cat -> stash
        (4, 14, ARCHIVE_CAT),   # not target, archived -> untouched
        (5, 15, 999),           # target, elsewhere -> pop
        (6, 16, None),          # target, no category -> pop
        (7, 17, 999),           # not target, elsewhere -> untouched
    ]
    pop, stash = compute_moves(connections, TEACHER_CAT, {1, 2, 5, 6})
    assert pop == [11, 15, 16]
    assert stash == [13]


def test_compute_moves_empty():
    assert compute_moves([], TEACHER_CAT, {1}) == ([], [])
    assert compute_moves([(1, 11, TEACHER_CAT)], TEACHER_CAT, set()) == ([], [11])

# endregion
