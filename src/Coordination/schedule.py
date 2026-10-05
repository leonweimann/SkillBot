"""
Pure calendar logic for the nightly teacher preparation.

This module contains no Discord or network code: it turns calendar events into a plan
(which students have an appointment today) and computes which channels have to be moved.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Optional


# region Events

_PHONE_CHARS = re.compile(r'^[+\d\s/().\-]+$')
_MIN_PHONE_DIGITS = 6
_NAME_SEPARATOR = re.compile(r'\s+mit\s+', re.IGNORECASE)
_UMLAUTS = str.maketrans({'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'ß': 'ss'})


@dataclass(frozen=True)
class CalendarEvent:
    """A calendar appointment reduced to the fields relevant for filtering and matching."""
    subject: str
    is_all_day: bool = False
    is_cancelled: bool = False
    is_online_meeting: bool = False
    location: str = ''
    categories: tuple[str, ...] = ()

    @classmethod
    def from_graph(cls, data: dict) -> 'CalendarEvent':
        """
        Build an event from a Microsoft Graph event dict.

        Tolerant to missing keys and ``None`` values.
        """
        data = data or {}
        location = data.get('location')
        location_name = location.get('displayName') if isinstance(location, dict) else location
        return cls(
            subject=str(data.get('subject') or ''),
            is_all_day=bool(data.get('isAllDay')),
            is_cancelled=bool(data.get('isCancelled')),
            is_online_meeting=bool(data.get('isOnlineMeeting')),
            location=str(location_name or ''),
            categories=tuple(str(c) for c in (data.get('categories') or []) if c),
        )


def _is_phone_number(location: str) -> bool:
    location = location.strip()
    if not location or not _PHONE_CHARS.match(location):
        return False
    return sum(ch.isdigit() for ch in location) >= _MIN_PHONE_DIGITS


def skip_reason(event: CalendarEvent) -> Optional[str]:
    """Return why an event is not a Discord appointment (German), or ``None`` if it is one."""
    if event.is_cancelled:
        return 'abgesagt'
    if event.is_all_day:
        return 'ganztägig'
    if event.is_online_meeting:
        return 'online-meeting'
    if any(c.strip().casefold() == 'telefon' for c in event.categories):
        return 'telefon'
    if _is_phone_number(event.location):
        return 'telefonnummer'
    return None

# endregion


# region Names

def extract_student_name(subject: str) -> Optional[str]:
    """Return the text after the first ' mit ' (case-insensitive) of ``<Fach> mit <Name>``, if any."""
    parts = _NAME_SEPARATOR.split(subject or '', maxsplit=1)
    if len(parts) < 2:
        return None
    name = ' '.join(parts[1].split())
    return name or None


def normalize_name(name: str) -> str:
    """Normalize a name for comparison: NFKC, casefold, transliterated umlauts, no hyphens, single spaces."""
    name = unicodedata.normalize('NFKC', name).casefold().translate(_UMLAUTS)
    name = name.replace('-', ' ').replace('_', ' ')
    return ' '.join(name.split())


def match_name(name: str, students: dict[int, str]) -> tuple[Optional[int], bool]:
    """
    Match a calendar name to a student.

    Args:
        name: Name taken from the calendar entry.
        students: student_id -> real_name.

    Returns:
        ``(student_id, ambiguous)``. First an exact normalized match is tried, then a unique student
        whose name tokens are a superset of the calendar name's tokens (at least 2 tokens).
        Several candidates yield ``(None, True)``, no candidate ``(None, False)``.
    """
    target = normalize_name(name)
    if not target:
        return None, False

    normalized = {sid: normalize_name(real) for sid, real in students.items()}

    exact = [sid for sid, norm in normalized.items() if norm == target]
    if exact:
        return (exact[0], False) if len(exact) == 1 else (None, True)

    tokens = set(target.split())
    if len(tokens) < 2:
        return None, False
    candidates = [sid for sid, norm in normalized.items() if tokens <= set(norm.split())]
    if len(candidates) == 1:
        return candidates[0], False
    return (None, True) if candidates else (None, False)

# endregion


# region Planning

@dataclass
class DayPlan:
    """Result of evaluating one day of calendar events."""
    student_ids: set[int] = field(default_factory=set)
    matched: dict[int, str] = field(default_factory=dict)  # student_id -> event subject
    skipped: list[tuple[str, str]] = field(default_factory=list)  # (subject, reason)
    unmatched: list[str] = field(default_factory=list)  # subjects with a name but no student
    ambiguous: list[str] = field(default_factory=list)


def plan_day(events: list[CalendarEvent], students: dict[int, str]) -> DayPlan:
    """
    Determine which students have an appointment.

    Args:
        events: All calendar events of the day.
        students: student_id -> real_name (only the teacher's students).
    """
    plan = DayPlan()
    for event in events:
        if reason := skip_reason(event):
            plan.skipped.append((event.subject, reason))
            continue

        name = extract_student_name(event.subject)
        if name is None:
            plan.skipped.append((event.subject, 'kein-titelmuster'))
            continue

        student_id, ambiguous = match_name(name, students)
        if ambiguous:
            plan.ambiguous.append(event.subject)
        elif student_id is None:
            plan.unmatched.append(event.subject)
        else:
            plan.student_ids.add(student_id)
            plan.matched.setdefault(student_id, event.subject)
    return plan


def compute_moves(connections: list[tuple[int, int, Optional[int]]], teacher_category_id: int,
                  target_student_ids: set[int]) -> tuple[list[int], list[int]]:
    """
    Decide which channels have to be moved.

    Args:
        connections: (student_id, channel_id, current_category_id) per student.
        teacher_category_id: The teacher's category.
        target_student_ids: Students that have an appointment.

    Returns:
        ``(channel_ids_to_pop, channel_ids_to_stash)``: targets outside the teacher category are popped,
        non-targets inside it are stashed. Everything else stays untouched.
    """
    pop, stash = [], []
    for student_id, channel_id, category_id in connections:
        in_teacher_category = category_id == teacher_category_id
        if student_id in target_student_ids:
            if not in_teacher_category:
                pop.append(channel_id)
        elif in_teacher_category:
            stash.append(channel_id)
    return pop, stash

# endregion
