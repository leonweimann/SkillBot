from cmds.CalendarGroup import build_calendar_choices, calendar_key, resolve_calendar

LONG_ID = 'AAMk' + 'x' * 200


def test_choice_values_fit_discord_limit_and_resolve_back():
    calendars = [(LONG_ID, 'Unterricht ' + 'n' * 150), ('short', 'Privat')]
    choices = build_calendar_choices(calendars)
    assert all(len(name) <= 100 and len(value) <= 100 for name, value in choices)
    assert resolve_calendar(calendars, choices[0][1]) == calendars[0]
    assert resolve_calendar(calendars, 'unknown') is None


def test_choices_filtered_by_current():
    calendars = [('a', 'Unterricht'), ('b', 'Privat')]
    assert build_calendar_choices(calendars, 'priv') == [('Privat', calendar_key('b'))]
