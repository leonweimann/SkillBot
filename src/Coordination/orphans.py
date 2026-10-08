"""
Detection and cleanup of orphaned teacher-student connections (`/dev orphans`).

A connection is orphaned when its student channel no longer exists on Discord. Before
`on_member_remove` purged leaving members, every student who left the server left such a row behind
(the nightly summary lists them as "Channel nicht gefunden").

- `build_report` classifies orphans without Discord or the database (unit-testable).
- `detect_orphans` reads the existing channels from Discord (`fetch_channels`, not the cache) and the
  membership of each affected student.
- `run_orphan_cleanup` is the whole command: dry run by default, with ``apply`` it purges the students who
  left the server (under the guild lock, so it cannot interleave with the nightly preparation). Students
  who are still members are never deleted, only listed.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field

import discord

import Utils.environment  # noqa: F401  (must be imported before Utils.lwlogging, circular import)
from Utils.channel_moves import get_guild_lock, retry_transient
from Utils.database import DatabaseError, DatabaseManager, Subuser, TeacherHasStudentsError, TeacherStudentConnection, User
from Utils.errors import CodeError
from Utils.lwlogging import log


MESSAGE_LIMIT = 1900          # Leave some headroom below Discord's 2000 character limit
_LOG_LIST_CHAR_LIMIT = 600    # Max characters per student list in the logs entry

FIX_HINT = ('↳ Der Channel fehlt, der Schüler ist aber noch auf dem Server: Der Lehrer trägt ihn mit '
            '`/students unassign` aus (geht auch ohne Channel) und ordnet ihn mit `/students assign` neu zu.')


# region Model

@dataclass(frozen=True)
class Orphan:
    """A teacher-student connection whose channel no longer exists."""
    teacher_id: int
    student_id: int
    channel_id: int
    real_name: str | None = None

    def label(self) -> str:
        """German description for listings; only the IDs if the student has no name (or no row)."""
        ids = f'Schüler `{self.student_id}`, Lehrer `{self.teacher_id}`, Channel `{self.channel_id}`'
        if self.real_name:
            return f'{discord.utils.escape_markdown(self.real_name)} ({ids})'
        return ids


@dataclass
class OrphanReport:
    """Result of the orphan detection."""
    checked: int                                               # Number of connections checked
    departed: list[Orphan] = field(default_factory=list)       # Student left the server -> purge
    still_members: list[Orphan] = field(default_factory=list)  # Student still a member -> never delete

    @property
    def departed_student_ids(self) -> list[int]:
        """IDs of the students to purge, each once, in listing order."""
        return list(dict.fromkeys(orphan.student_id for orphan in self.departed))


@dataclass
class CleanupResult:
    """Result of `run_orphan_cleanup` with ``apply=True``."""
    purged: dict[int, dict[str, int]] = field(default_factory=dict)  # student ID -> deleted rows per table
    failed: dict[int, str] = field(default_factory=dict)             # student ID -> German reason

# endregion


# region Detection

def build_report(connections: Iterable[TeacherStudentConnection], existing_channel_ids: set[int],
                 member_ids: set[int], names: dict[int, str | None]) -> OrphanReport:
    """
    Finds and classifies the connections whose channel no longer exists.

    Args:
        connections (Iterable[TeacherStudentConnection]): All connections of the guild (anything with
            ``teacher_id``, ``student_id`` and ``channel_id``).
        existing_channel_ids (set[int]): IDs of all channels that exist on Discord.
        member_ids (set[int]): IDs of the affected students who are still members of the guild.
        names (dict[int, str | None]): Real names by student ID (missing or None: only IDs are shown).

    Returns:
        OrphanReport: Orphans of departed students and of students who are still members.
    """
    connections = list(connections)
    report = OrphanReport(checked=len(connections))
    for connection in connections:
        if connection.channel_id in existing_channel_ids:
            continue
        orphan = Orphan(connection.teacher_id, connection.student_id, connection.channel_id,
                        names.get(connection.student_id))
        if connection.student_id in member_ids:
            report.still_members.append(orphan)
        else:
            report.departed.append(orphan)
    return report


async def is_guild_member(guild: discord.Guild, user_id: int) -> bool:
    """
    Checks whether a user is still a member of the guild (cache first, then Discord).

    Raises:
        discord.HTTPException: If Discord could not answer (anything except "unknown member"), so an
            unclear membership never counts as departed.
    """
    if guild.get_member(user_id) is not None:
        return True
    try:
        await retry_transient(lambda: guild.fetch_member(user_id))
        return True
    except discord.NotFound:
        return False


async def is_student_present(guild: discord.Guild, student_id: int) -> bool:
    """
    Checks whether a student is still on the server with any account: the main account or a connected
    second account (``subusers``). Only a student without any remaining account counts as departed.

    Raises:
        discord.HTTPException: If Discord could not answer for one of the accounts.
    """
    if await is_guild_member(guild, student_id):
        return True
    for subuser in Subuser.get_all_subusers(guild.id, student_id):
        if await is_guild_member(guild, subuser.subuser_id):
            return True
    return False


async def detect_orphans(guild: discord.Guild) -> OrphanReport:
    """
    Detects orphaned connections using Discord's current channels and members (not the cache only).

    Args:
        guild (discord.Guild): The guild to check.

    Returns:
        OrphanReport: The classified orphans.

    Raises:
        CodeError: If Discord returned no channels at all (would mark every connection as orphaned).
    """
    channels = await retry_transient(guild.fetch_channels)
    if not channels:
        raise CodeError('Discord hat keine Channels geliefert, Prüfung abgebrochen')
    existing_channel_ids = {channel.id for channel in channels}

    connections = TeacherStudentConnection.get_all(guild.id)
    affected = list(dict.fromkeys(c.student_id for c in connections if c.channel_id not in existing_channel_ids))
    member_ids = {student_id for student_id in affected if await is_student_present(guild, student_id)}
    names = {student_id: User(guild.id, student_id).real_name for student_id in affected}
    return build_report(connections, existing_channel_ids, member_ids, names)

# endregion


# region Cleanup

def purge_departed(guild_id: int, report: OrphanReport) -> CleanupResult:
    """
    Purges every student of ``report.departed`` (each in its own transaction).

    Students who are still members are not touched. A departed student who is also a teacher with
    students is refused by `DatabaseManager.purge_user` and reported as failed.
    """
    result = CleanupResult()
    for student_id in report.departed_student_ids:
        try:
            result.purged[student_id] = DatabaseManager.purge_user(guild_id, student_id)
        except TeacherHasStudentsError as e:
            result.failed[student_id] = f'ist Lehrer mit {e.student_count} Schüler(n)'
        except DatabaseError as e:
            result.failed[student_id] = str(e)
    return result


async def run_orphan_cleanup(guild: discord.Guild, apply: bool, actor: discord.abc.User) -> str:
    """
    Runs `/dev orphans`: lists orphaned connections and, with ``apply``, purges the departed students.

    With ``apply`` detection and purge run under the guild lock and one entry is written to the logs
    channel.

    Args:
        guild (discord.Guild): The guild to clean up.
        apply (bool): Whether to delete (otherwise dry run).
        actor (discord.abc.User): Who ran the command (for the logs entry).

    Returns:
        str: The German reply, shorter than Discord's 2000 character limit.
    """
    if not apply:
        return format_report(await detect_orphans(guild))

    async with get_guild_lock(guild.id):
        report = await detect_orphans(guild)
        result = purge_departed(guild.id, report)

    message = format_report(report, result)
    try:
        await log(guild, 'Verwaiste Schüler-Einträge bereinigt (/dev orphans)', details=_log_details(report, result, actor))
    except Exception as e:  # The purge is done, the reply must still say what was deleted
        message = _fit(f'{message}\n⚠️ Log-Eintrag fehlgeschlagen: {e}')
    return message

# endregion


# region Formatting

def _bullets(items: list[str], budget: int) -> list[str]:
    """Bullet lines with at most ``budget`` characters in total, the rest as "+n weitere"."""
    lines: list[str] = []
    used = 0
    for index, item in enumerate(items):
        line = f'• {item}'
        rest = len(items) - index - 1
        reserve = len(f'• … +{rest} weitere') + 1 if rest else 0
        if used + len(line) + 1 + reserve > budget:
            lines.append(f'• … +{len(items) - index} weitere')
            break
        lines.append(line)
        used += len(line) + 1
    return lines


def _fit(message: str) -> str:
    """Hard limit as a last resort (the lists are already truncated)."""
    return message if len(message) <= MESSAGE_LIMIT else message[:MESSAGE_LIMIT - 1] + '…'


def format_report(report: OrphanReport, result: CleanupResult | None = None) -> str:
    """
    Formats the German reply of `/dev orphans`.

    Args:
        report (OrphanReport): The detected orphans.
        result (CleanupResult | None): The purge result, None for a dry run.

    Returns:
        str: The reply, at most ``MESSAGE_LIMIT`` characters (long lists end with "+n weitere").
    """
    orphan_count = len(report.departed) + len(report.still_members)
    if not orphan_count:
        return f'✅ Keine verwaisten Schüler-Einträge gefunden ({report.checked} Verbindungen geprüft).'

    head = ['🔍 **Verwaiste Schüler-Einträge** – Vorschau, es wurde nichts gelöscht.' if result is None
            else '🧹 **Verwaiste Schüler-Einträge bereinigt**',
            f'Geprüft: {report.checked} Verbindungen, davon {orphan_count} ohne Channel.']
    sections: list[tuple[str, list[str], str | None]] = []  # (header, items, footer)

    if result is None:
        if report.departed:
            sections.append((f'🗑️ Würde löschen ({len(report.departed)}) – Schüler hat den Server verlassen:',
                             [o.label() for o in report.departed], None))
    else:
        deleted = [o for o in report.departed if o.student_id in result.purged]
        failed = [o for o in report.departed if o.student_id in result.failed]
        if deleted:
            sections.append((f'🗑️ Gelöscht ({len(deleted)}):', [o.label() for o in deleted], None))
        if failed:
            sections.append((f'❌ Fehlgeschlagen ({len(failed)}):',
                             [f'{o.label()} – {result.failed[o.student_id]}' for o in failed], None))
    if report.still_members:
        sections.append((f'⚠️ Nicht gelöscht – Schüler noch auf dem Server ({len(report.still_members)}):',
                         [o.label() for o in report.still_members], FIX_HINT))

    tail = ['Zum Löschen: `/dev orphans apply:True`'] if result is None and report.departed else []

    # Share the remaining characters between the lists, shortest first, so unused space goes to longer lists
    fixed = head + tail + [s[0] for s in sections] + [s[2] for s in sections if s[2]]
    available = MESSAGE_LIMIT - sum(len(line) + 1 for line in fixed)
    bullets: dict[int, list[str]] = {}
    by_length = sorted(range(len(sections)), key=lambda i: sum(len(item) + 3 for item in sections[i][1]))
    for position, index in enumerate(by_length):
        bullets[index] = _bullets(sections[index][1], available // (len(sections) - position))
        available -= sum(len(line) + 1 for line in bullets[index])

    lines = list(head)
    for index, (header, _, footer) in enumerate(sections):
        lines.append(header)
        lines.extend(bullets[index])
        if footer:
            lines.append(footer)
    lines.extend(tail)
    return _fit('\n'.join(lines))


def _log_details(report: OrphanReport, result: CleanupResult, actor: discord.abc.User) -> dict[str, str]:
    """Details of the logs entry after a cleanup (inside a code block, so plain text without mentions)."""
    def names(student_ids: Iterable[int]) -> str:
        by_id = {o.student_id: o.real_name for o in report.departed + report.still_members}
        items = [f'{by_id.get(sid) or "?"} ({sid})' for sid in student_ids]
        text = ', '.join(items)
        if len(text) > _LOG_LIST_CHAR_LIMIT:
            text = text[:_LOG_LIST_CHAR_LIMIT - 1] + '…'
        return text or '-'

    return {
        'Ausgeführt von': f'{actor} ({actor.id})',
        'Geprüft': f'{report.checked} Verbindungen',
        'Gelöscht': f'{len(result.purged)} Schüler: {names(result.purged)}',
        'Fehlgeschlagen': f'{len(result.failed)}: {names(result.failed)}' if result.failed else '0',
        'Noch auf dem Server': f'{len(report.still_members)} Verbindung(en), nicht gelöscht',
    }

# endregion
