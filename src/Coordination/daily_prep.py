"""
Calendar-driven preparation of a teacher's category.

`prepare_teacher` moves the channels of students with an appointment today into the teacher's
category and archives all other channels of that teacher. `stash_all` archives every student channel
in a teacher's category (nightly run for teachers without a calendar). `pop_to_teacher` moves a single
archived channel back into its teacher's category (used by the auto-pop).

All channel moves of a guild are serialised by `get_guild_lock`.
"""

import asyncio
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

import discord

import Utils.environment  # noqa: F401  (must be imported before Utils.lwlogging, circular import)
from Coordination.schedule import CalendarEvent, DayPlan, compute_moves, plan_day
from Coordination.sorting import channel_sorting_coordinator
from Utils import msgraph
from Utils.archive import ArchiveCategory
from Utils.database import Archive, Student, Subuser, Teacher, TeacherCalendar, TeacherStudentConnection
from Utils.errors import CodeError, UsageError
from Utils.lwlogging import log


BERLIN = ZoneInfo('Europe/Berlin')

_SUMMARY_LIMIT = 1900          # Leave some headroom below Discord's 2000 character limit
_LIST_CHAR_LIMIT = 250         # Max characters per listed group in the summary
_ITEM_CHAR_LIMIT = 80          # Max characters per single listed item


# region Locks & Helpers

_guild_locks: dict[int, asyncio.Lock] = {}


def get_guild_lock(guild_id: int) -> asyncio.Lock:
    """
    Returns the lock that serialises all channel moves within a guild.

    Args:
        guild_id (int): The ID of the guild.

    Returns:
        asyncio.Lock: The same lock instance for every call with the same guild ID.
    """
    lock = _guild_locks.get(guild_id)
    if lock is None:
        lock = _guild_locks[guild_id] = asyncio.Lock()
    return lock


def is_archived_category(guild: discord.Guild, category_id: Optional[int]) -> bool:
    """
    Checks whether the given category is one of the guild's archive categories.

    Only the database is consulted, no Discord API call is made.

    Args:
        guild (discord.Guild): The guild the category belongs to.
        category_id (Optional[int]): The ID of the category (``None`` for channels without category).

    Returns:
        bool: True if the category is a registered archive category, False otherwise.
    """
    if category_id is None:
        return False
    return any(archive.id == category_id for archive in Archive.get_all(guild.id))


def _get_teacher_category(guild: discord.Guild, teacher_id: int) -> Optional[discord.CategoryChannel]:
    """Returns the teacher's teaching category from the guild cache, or ``None``."""
    db_teacher = Teacher(guild.id, teacher_id)
    if not db_teacher.teaching_category:
        return None
    return discord.utils.get(guild.categories, id=db_teacher.teaching_category)


def get_cmd_channel(guild: discord.Guild, teacher_id: int) -> Optional[discord.TextChannel]:
    """
    Returns the teacher's ``cmd`` channel (inside the teacher's teaching category).

    Args:
        guild (discord.Guild): The guild of the teacher.
        teacher_id (int): The ID of the teacher.

    Returns:
        Optional[discord.TextChannel]: The ``cmd`` channel, or ``None`` if the teacher has no
        category or the category has no ``cmd`` channel.
    """
    category = _get_teacher_category(guild, teacher_id)
    if category is None:
        return None
    return discord.utils.get(category.text_channels, name='cmd')


async def _safe_log(guild: discord.Guild, message: str, details: dict[str, str] = {}):
    """Logs to the guild's logs channel without ever raising."""
    try:
        await log(guild, message, details)
    except Exception as e:
        print(f'[daily_prep] Failed to log "{message}" in guild {guild.id}: {e}')


async def _safe_sort(guild: discord.Guild, category: discord.CategoryChannel):
    """Sorts a category; failures are logged instead of raised (the moves already happened)."""
    try:
        await channel_sorting_coordinator.sort_channels_in_category(category)
    except Exception as e:
        await _safe_log(guild, f'[ERROR] Sortieren der Kategorie {category.name} fehlgeschlagen', {'error': str(e)})

# endregion


# region Preparation

@dataclass
class PrepResult:
    """Outcome of a (possibly simulated) preparation of one teacher's category."""
    plan: DayPlan
    popped: list[str] = field(default_factory=list)    # channel names moved into the teacher category
    stashed: list[str] = field(default_factory=list)   # channel names moved into an archive
    missing: list[str] = field(default_factory=list)   # students whose channel was not found
    failed: list[str] = field(default_factory=list)    # channel names whose move failed


def _load_students(guild: discord.Guild, teacher_id: int) -> tuple[list[TeacherStudentConnection], dict[int, Optional[str]]]:
    """Returns the teacher's student connections and the students' real names (student_id -> name)."""
    connections = TeacherStudentConnection.find_all_by_teacher(guild.id, teacher_id)
    student_names: dict[int, Optional[str]] = {
        con.student_id: Student(guild.id, con.student_id).real_name for con in connections
    }
    return connections, student_names


async def _move_channels(guild: discord.Guild, teacher_id: int, teacher_category: discord.CategoryChannel,
                         connections: list[TeacherStudentConnection], student_names: dict[int, Optional[str]],
                         target_student_ids: set[int], result: PrepResult, *, dry_run: bool, reason: str,
                         log_problems: bool):
    """
    Moves the teacher's channels so that exactly the target students are in the teacher's category.

    Channels of target students outside the teacher category are popped, channels of all other students
    inside the teacher category are archived; everything else (``cmd``, foreign channels, already archived
    channels) stays untouched. Runs under the guild lock and fills ``result`` in place.

    Args:
        guild (discord.Guild): The guild of the teacher.
        teacher_id (int): The ID of the teacher.
        teacher_category (discord.CategoryChannel): The teacher's teaching category.
        connections (list[TeacherStudentConnection]): The teacher's student connections.
        student_names (dict[int, Optional[str]]): student_id -> real name (used for missing channels).
        target_student_ids (set[int]): Students whose channel belongs into the teacher category.
            An empty set archives every student channel of the teacher category.
        result (PrepResult): Receives the (planned) moves, missing channels and failures.
        dry_run (bool): If True, only record what would be moved.
        reason (str): The audit log reason for the channel edits.
        log_problems (bool): Whether every missing channel and failed move is logged individually.
            If False, problems are only collected in ``result`` (the caller reports them).

    Students currently waiting in the lounge always count as targets. They are read under the lock, so
    a lounge pop that ran just before can never be undone by this run.
    """
    async with get_guild_lock(guild.id):
        target_student_ids = target_student_ids | students_in_lounge(guild)
        channels: dict[int, discord.TextChannel] = {}
        moves_input: list[tuple[int, int, Optional[int]]] = []
        for con in connections:
            channel = discord.utils.get(guild.text_channels, id=con.channel_id)
            if channel is None:
                result.missing.append(student_names.get(con.student_id) or str(con.student_id))
                if log_problems:
                    await _safe_log(
                        guild,
                        f"Channel für Schüler <@{con.student_id}> nicht gefunden, sollte aber `{con.channel_id}` sein",
                        {'Lehrer': f'<@{teacher_id}>', 'Vorgang': 'Tagesvorbereitung'}
                    )
                continue
            channels[channel.id] = channel
            moves_input.append((con.student_id, channel.id, channel.category_id))

        pop_ids, stash_ids = compute_moves(moves_input, teacher_category.id, target_student_ids)

        if dry_run:
            result.popped = [channels[cid].name for cid in pop_ids]
            result.stashed = [channels[cid].name for cid in stash_ids]
            return

        for cid in pop_ids:
            channel = channels[cid]
            try:
                await channel.edit(category=teacher_category, reason=reason)
                result.popped.append(channel.name)
            except Exception as e:
                result.failed.append(channel.name)
                if log_problems:
                    await _safe_log(guild, f"[ERROR] Konnte {channel.mention} nicht in die Lehrer-Kategorie verschieben", {'error': str(e)})
                else:
                    print(f'[daily_prep] Failed to move channel {channel.id} into the teacher category: {e}')

        touched_archives: dict[int, discord.CategoryChannel] = {}
        for cid in stash_ids:
            channel = channels[cid]
            try:
                # Re-make per channel so a full archive rolls over to a new one
                archive = await ArchiveCategory.make(guild)
                archive_category = await archive.add_channel(channel)
                touched_archives[archive_category.id] = archive_category
                result.stashed.append(channel.name)
            except Exception as e:
                result.failed.append(channel.name)
                if log_problems:
                    await _safe_log(guild, f"[ERROR] Konnte {channel.mention} nicht archivieren", {'error': str(e)})
                else:
                    print(f'[daily_prep] Failed to archive channel {channel.id}: {e}')

        # Sorting fetches fresh channel data itself (the cache lags behind the HTTP calls)
        if result.popped or result.stashed:
            await _safe_sort(guild, teacher_category)
        for category in touched_archives.values():
            await _safe_sort(guild, category)


async def prepare_teacher(guild: discord.Guild, teacher_id: int, day: date, dry_run: bool = False) -> PrepResult:
    """
    Prepares the teacher's category for the given day based on the linked calendar.

    Students with an appointment on ``day`` get their channel moved into the teacher's category,
    all other channels of the teacher that are currently in the teacher's category are archived.

    Safety rule: the calendar is fetched before any channel is touched. Any Graph error propagates
    and nothing is moved.

    Args:
        guild (discord.Guild): The guild of the teacher.
        teacher_id (int): The ID of the teacher.
        day (date): The day to prepare (Europe/Berlin).
        dry_run (bool): If True, only compute what would be moved; nothing is edited and
            ``last_prepared_date`` is not updated.

    Returns:
        PrepResult: The day plan and the (planned) moves.

    Raises:
        UsageError: If the teacher has no linked calendar or no selected calendar.
        CodeError: If the teacher has no teaching category.
        msgraph.GraphAuthError, msgraph.GraphError, msgraph.GraphNotConfiguredError: Calendar errors.
    """
    db_cal = TeacherCalendar(guild.id, teacher_id)
    if not db_cal.is_ready:
        raise UsageError(
            "Kein Kalender verknüpft oder ausgewählt. "
            "Bitte zuerst `/calendar connect` und danach `/calendar select` verwenden."
        )

    teacher_category = _get_teacher_category(guild, teacher_id)
    if teacher_category is None:
        raise CodeError(f"Lehrer {teacher_id} hat keine Kategorie")

    # 1. Fetch the calendar BEFORE touching anything (errors propagate, nothing moves)
    start = datetime.combine(day, time(0, 0), tzinfo=BERLIN)
    end = datetime.combine(day + timedelta(days=1), time(0, 0), tzinfo=BERLIN)
    raw_events = await msgraph.get_events(db_cal, start, end)
    events = [CalendarEvent.from_graph(e) for e in raw_events]

    # 2. Plan the day
    connections, student_names = _load_students(guild, teacher_id)
    plan = plan_day(events, {sid: name for sid, name in student_names.items() if name})
    result = PrepResult(plan=plan)

    # 3. Move channels
    await _move_channels(
        guild, teacher_id, teacher_category, connections, student_names, plan.student_ids, result,
        dry_run=dry_run, reason=f'Tagesvorbereitung {day.isoformat()}', log_problems=True
    )
    if dry_run:
        return result

    # 4. Remember the prepared day
    db_cal.edit(last_prepared_date=day.isoformat())
    return result


async def stash_all(guild: discord.Guild, teacher_id: int) -> PrepResult:
    """
    Archives every student channel that is currently in the teacher's category.

    Used at night for teachers without a ready calendar. The ``cmd`` channel and channels that do not
    belong to a student of the teacher stay untouched, and the calendar data (``last_prepared_date``) is
    not touched. Students waiting in the lounge are the only exception: their channel stays (or is popped). Missing channels and failed moves are only collected in the
    result, not logged individually.

    Args:
        guild (discord.Guild): The guild of the teacher.
        teacher_id (int): The ID of the teacher.

    Returns:
        PrepResult: An empty day plan and the archived, missing and failed channels.

    Raises:
        CodeError: If the teacher has no teaching category.
    """
    teacher_category = _get_teacher_category(guild, teacher_id)
    if teacher_category is None:
        raise CodeError(f"Lehrer {teacher_id} hat keine Kategorie")

    connections, student_names = _load_students(guild, teacher_id)
    result = PrepResult(plan=DayPlan())
    await _move_channels(
        guild, teacher_id, teacher_category, connections, student_names, set(), result,
        dry_run=False, reason=f'Nächtliches Archivieren {datetime.now(BERLIN).date().isoformat()}',
        log_problems=False
    )
    return result


LOUNGE_CHANNEL_NAME = 'lounge'  # Voice channel that serves as the waiting room


def resolve_student_id(guild_id: int, member_id: int) -> int:
    """
    Maps a connected sub-account to its main user.

    Args:
        guild_id (int): The ID of the guild.
        member_id (int): The ID of the member.

    Returns:
        int: The ID of the main user if the member is a sub-account, otherwise ``member_id``.
    """
    user = Subuser.get_user_of_subuser(guild_id, member_id)
    return user.id if user is not None else member_id


def students_in_lounge(guild: discord.Guild) -> set[int]:
    """
    Returns the ids of the students currently waiting in the lounge (from the cache).

    Connected sub-accounts are resolved to their main student; bots are ignored.
    """
    lounge = discord.utils.get(guild.voice_channels, name=LOUNGE_CHANNEL_NAME)
    if lounge is None:
        return set()
    return {resolve_student_id(guild.id, member.id) for member in lounge.members if not member.bot}


async def pop_to_teacher(guild: discord.Guild, ts_con: TeacherStudentConnection,
                         reason: str = 'Auto-Pop: Nachricht im archivierten Channel') -> bool:
    """
    Moves an archived student channel back into its teacher's category.

    The channel is re-fetched from the API to get its authoritative category.

    Args:
        guild (discord.Guild): The guild of the channel.
        ts_con (TeacherStudentConnection): The connection of the student channel.
        reason (str): Reason shown in Discord's audit log.

    Returns:
        bool: True if the channel was moved, False if it was not in an archive category
        (or does not exist anymore).

    Raises:
        CodeError: If the teacher has no teaching category.
    """
    async with get_guild_lock(guild.id):
        try:
            channel = await guild.fetch_channel(ts_con.channel_id)
        except discord.NotFound:
            return False

        if not isinstance(channel, discord.TextChannel) or not is_archived_category(guild, channel.category_id):
            return False

        teacher_category = _get_teacher_category(guild, ts_con.teacher_id)
        if teacher_category is None:
            raise CodeError(f"Lehrer {ts_con.teacher_id} hat keine Kategorie")

        await channel.edit(category=teacher_category, reason=reason)
        await _safe_sort(guild, teacher_category)
    return True

# endregion


# region Summary

def _code(item: str) -> str:
    item = ' '.join(str(item).split()).replace('`', "'")
    if len(item) > _ITEM_CHAR_LIMIT:
        item = item[:_ITEM_CHAR_LIMIT - 1] + '…'
    return f'`{item}`'


def _join_limited(items: list[str], limit: int = _LIST_CHAR_LIMIT) -> str:
    """Joins items as inline code, truncated to ``limit`` characters with a "+n weitere" suffix."""
    parts: list[str] = []
    length = 0
    for index, item in enumerate(items):
        piece = _code(item)
        extra = len(piece) + (2 if parts else 0)
        if length + extra > limit:
            parts.append(f'… (+{len(items) - index} weitere)')
            break
        parts.append(piece)
        length += extra
    return ', '.join(parts)


def _join_plain(items: list[str], limit: int = _LIST_CHAR_LIMIT) -> str:
    """Joins items with commas (no markdown, for code blocks), truncated with a "+n weitere" suffix."""
    parts: list[str] = []
    length = 0
    for index, item in enumerate(items):
        piece = ' '.join(str(item).split()).replace('`', "'")[:_ITEM_CHAR_LIMIT]
        extra = len(piece) + (2 if parts else 0)
        if length + extra > limit:
            parts.append(f'… (+{len(items) - index} weitere)')
            break
        parts.append(piece)
        length += extra
    return ', '.join(parts)


def format_stash_details(teacher_id: int, result: PrepResult) -> dict[str, str]:
    """
    Formats the log details of a nightly `stash_all` run (compact, German).

    Args:
        teacher_id (int): The ID of the teacher.
        result (PrepResult): The result of `stash_all`.

    Returns:
        dict[str, str]: Details for the logs channel; empty groups are left out.
    """
    details = {'Lehrer': f'<@{teacher_id}>'}
    if result.stashed:
        details['Archiviert'] = f'{len(result.stashed)}: {_join_plain(result.stashed)}'
    if result.failed:
        details['Fehlgeschlagen'] = f'{len(result.failed)}: {_join_plain(result.failed)}'
    if result.missing:
        details['Nicht gefunden'] = f'{len(result.missing)}: {_join_plain(result.missing)}'
    return details


def format_summary(result: PrepResult, dry_run: bool) -> str:
    """
    Formats a compact German summary of a preparation for the teacher's ``cmd`` channel.

    Args:
        result (PrepResult): The preparation result.
        dry_run (bool): Whether the result comes from a dry run (nothing was moved).

    Returns:
        str: The summary, always shorter than Discord's 2000 character limit.
    """
    plan = result.plan
    lines: list[str] = []

    if dry_run:
        lines.append('🔍 **Vorschau Tagesvorbereitung** – es wurde nichts verschoben.')
    else:
        lines.append('📅 **Tagesvorbereitung abgeschlossen**')

    lines.append(f'Termine mit Schülern erkannt: **{len(plan.matched)}**')

    pop_label = 'Würde hereinholen' if dry_run else 'Hereingeholt'
    stash_label = 'Würde archivieren' if dry_run else 'Archiviert'
    if result.popped:
        lines.append(f'📥 {pop_label} ({len(result.popped)}): {_join_limited(result.popped)}')
    if result.stashed:
        lines.append(f'📦 {stash_label} ({len(result.stashed)}): {_join_limited(result.stashed)}')
    if not result.popped and not result.stashed:
        lines.append('Keine Channel-Verschiebungen nötig.')

    if result.failed:
        lines.append(f'⚠️ Verschieben fehlgeschlagen ({len(result.failed)}): {_join_limited(result.failed)}')
    if result.missing:
        lines.append(f'⚠️ Channel nicht gefunden ({len(result.missing)}): {_join_limited(result.missing)}')
    if plan.unmatched:
        lines.append(f'❓ Kein Schüler gefunden ({len(plan.unmatched)}): {_join_limited(plan.unmatched)}')
    if plan.ambiguous:
        lines.append(f'❓ Mehrdeutig ({len(plan.ambiguous)}): {_join_limited(plan.ambiguous)}')
    if plan.skipped:
        reasons = Counter(reason for _, reason in plan.skipped)
        details = ', '.join(f'{count}× {reason}' for reason, count in reasons.most_common())
        lines.append(f'⏭️ Übersprungen ({len(plan.skipped)}): {details}')

    summary = '\n'.join(lines)
    if len(summary) > _SUMMARY_LIMIT:
        summary = summary[:_SUMMARY_LIMIT - 1] + '…'
    return summary

# endregion
