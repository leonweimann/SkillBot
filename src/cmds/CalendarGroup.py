import asyncio
import hashlib
import time
from datetime import datetime

import discord
from discord import app_commands

import Utils.environment as env
import Utils.msgraph as msgraph
import Coordination.daily_prep as prep
from Utils.database import Teacher, TeacherCalendar
from Utils.errors import UsageError

CALENDAR_CACHE_TTL_SECONDS = 60
NIGHTLY_PREP_TIME = '04:00'

# (guild_id, user_id) -> (timestamp, [(calendar_id, calendar_name)])
_calendar_cache: dict[tuple[int, int], tuple[float, list[tuple[str, str]]]] = {}
# Strong references to background tasks so they are not garbage collected
_background_tasks: set[asyncio.Task] = set()


def calendar_key(calendar_id: str) -> str:
    """Short, stable choice value for a calendar id (Discord limits values to 100 chars)."""
    return hashlib.sha1(calendar_id.encode('utf-8')).hexdigest()[:16]


def build_calendar_choices(calendars: list[tuple[str, str]], current: str = '') -> list[tuple[str, str]]:
    """(name, key) pairs, filtered by `current`, limited to Discord's 25 choices and 100 char names."""
    needle = current.casefold()
    return [
        (name[:100] or '(ohne Namen)', calendar_key(cal_id))
        for cal_id, name in calendars
        if needle in name.casefold()
    ][:25]


def resolve_calendar(calendars: list[tuple[str, str]], key: str) -> tuple[str, str] | None:
    for cal_id, name in calendars:
        if calendar_key(cal_id) == key:
            return cal_id, name
    return None


async def _get_calendars(guild_id: int, user_id: int, db_cal: TeacherCalendar, use_cache: bool = True) -> list[tuple[str, str]]:
    cache_key = (guild_id, user_id)
    cached = _calendar_cache.get(cache_key)
    if use_cache and cached and time.monotonic() - cached[0] < CALENDAR_CACHE_TTL_SECONDS:
        return cached[1]
    calendars = await msgraph.list_calendars(db_cal)
    _calendar_cache[cache_key] = (time.monotonic(), calendars)
    return calendars


def _raise_graph_error(error: Exception):
    """Translates Graph errors into UsageErrors (never leaks tokens or raw API bodies)."""
    if isinstance(error, msgraph.GraphNotConfiguredError):
        raise UsageError('Die Microsoft-Anbindung ist nicht konfiguriert. Bitte einen Admin, `MS_CLIENT_ID` und `MS_TENANT_ID` zu setzen.') from error
    if isinstance(error, msgraph.GraphAuthError):
        raise UsageError('Die Kalender-Verbindung ist abgelaufen oder ungültig. Bitte führe `/calendar connect` erneut aus.') from error
    if isinstance(error, msgraph.GraphError):
        raise UsageError('Der Kalender konnte nicht abgerufen werden. Bitte versuche es später erneut.') from error
    raise error


def _require_linked(interaction: discord.Interaction) -> TeacherCalendar:
    db_cal = TeacherCalendar(interaction.guild.id, interaction.user.id)
    if not db_cal.is_linked:
        raise UsageError('Es ist noch kein Kalender verknüpft. Bitte führe zuerst `/calendar connect` aus.')
    return db_cal


def _require_ready(interaction: discord.Interaction) -> TeacherCalendar:
    db_cal = _require_linked(interaction)
    if not db_cal.calendar_id:
        raise UsageError('Es ist noch kein Kalender ausgewählt. Bitte führe `/calendar select` aus.')
    return db_cal


async def _notify_teacher(guild: discord.Guild, member: discord.Member, text: str):
    """Posts into the teacher's cmd channel, falls back to a DM."""
    content = f'{member.mention} {text}'
    try:
        channel = prep.get_cmd_channel(guild, member.id)
        if channel is not None:
            await channel.send(content)
            return
        await member.send(text)
    except discord.HTTPException:
        pass


async def _finish_connect(guild: discord.Guild, member: discord.Member, flow: dict):
    try:
        token_cache = await msgraph.complete_device_flow(flow)
        teacher = Teacher(guild.id, member.id)
        if teacher.teaching_category is None:
            raise UsageError('Du bist nicht als Lehrer registriert.')
        db_cal = TeacherCalendar(guild.id, member.id)
        db_cal.link(token_cache)
        _calendar_cache.pop((guild.id, member.id), None)
    except msgraph.GraphAuthError:
        await _notify_teacher(guild, member, env.failure_response(
            'Die Anmeldung bei Microsoft ist fehlgeschlagen oder abgelaufen. Bitte starte `/calendar connect` erneut.'))
        return
    except UsageError as e:
        await _notify_teacher(guild, member, env.failure_response(str(e)))
        return
    except Exception as e:
        await env.log(guild, env.failure_response('Kalender-Verknüpfung fehlgeschlagen.'),
                      details={'Command': 'calendar connect', 'Used by': member.mention, 'Error': type(e).__name__})
        await _notify_teacher(guild, member, env.failure_response('Die Kalender-Verknüpfung ist fehlgeschlagen.'))
        return
    await _notify_teacher(guild, member, env.success_response(
        'Dein Microsoft-Konto ist verknüpft. Nächster Schritt: Wähle mit `/calendar select` deinen Kalender aus.'))
    # Warm the cache: the select autocomplete must answer within 3 s
    try:
        await _get_calendars(guild.id, member.id, db_cal, use_cache=False)
    except Exception:
        pass


@app_commands.guild_only()
class CalendarGroup(app_commands.Group):
    # region Connect

    @app_commands.command(
        name='connect',
        description='Verknüpft dein Microsoft-365-Konto mit dem Bot.'
    )
    @app_commands.checks.has_role('Lehrer')
    async def connect(self, interaction: discord.Interaction):
        if not msgraph.is_configured():
            await env.send_safe_response(interaction, env.failure_response(
                'Die Microsoft-Anbindung ist nicht konfiguriert. Ein Admin muss `MS_CLIENT_ID` und `MS_TENANT_ID` setzen.'), ephemeral=True)
            return

        if Teacher(interaction.guild.id, interaction.user.id).teaching_category is None:
            raise UsageError('Du bist nicht als Lehrer registriert.')

        # Starting the device flow talks to Microsoft and may exceed the 3 s interaction deadline
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            flow = await msgraph.start_device_flow()
        except Exception as e:
            _raise_graph_error(e)

        await env.send_safe_response(
            interaction,
            f"{flow['message']}\n\nNach der Anmeldung schreibe ich dir in deinen `cmd`-Kanal. "
            "Der Code ist ca. 15 Minuten gültig.",
            ephemeral=True
        )

        task = asyncio.create_task(_finish_connect(interaction.guild, interaction.user, flow))
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)

    @connect.error
    async def connect_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        await env.handle_app_command_error(
            interaction, error, command_name='calendar connect', reqired_role='Lehrer'
        )

    # endregion Connect

    # region Select

    @app_commands.command(
        name='select',
        description='Wählt den Kalender für die automatische Tagesvorbereitung.'
    )
    @app_commands.describe(calendar='Der Kalender mit deinen Terminen')
    @app_commands.checks.has_role('Lehrer')
    async def select(self, interaction: discord.Interaction, calendar: str):
        db_cal = _require_linked(interaction)
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            calendars = await _get_calendars(interaction.guild.id, interaction.user.id, db_cal)
            found = resolve_calendar(calendars, calendar)
            if found is None:  # stale key: refetch once
                calendars = await _get_calendars(interaction.guild.id, interaction.user.id, db_cal, use_cache=False)
                found = resolve_calendar(calendars, calendar)
        except (msgraph.GraphError, msgraph.GraphAuthError, msgraph.GraphNotConfiguredError) as e:
            _raise_graph_error(e)
        if found is None:
            raise UsageError('Dieser Kalender wurde nicht gefunden. Bitte wähle ihn aus der Vorschlagsliste aus.')

        cal_id, cal_name = found
        db_cal.edit(calendar_id=cal_id, calendar_name=cal_name)
        await env.send_safe_response(
            interaction,
            env.success_response(f'Kalender **{cal_name}** ausgewählt. Mit `/calendar preview` kannst du testen, was heute passieren würde.'),
            ephemeral=True
        )

    @select.autocomplete('calendar')
    async def select_calendar_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        try:
            db_cal = TeacherCalendar(interaction.guild.id, interaction.user.id)
            if not db_cal.is_linked:
                return []
            calendars = await _get_calendars(interaction.guild.id, interaction.user.id, db_cal)
            return [app_commands.Choice(name=name, value=key) for name, key in build_calendar_choices(calendars, current)]
        except Exception:
            return []

    @select.error
    async def select_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        await env.handle_app_command_error(
            interaction, error, command_name='calendar select', reqired_role='Lehrer'
        )

    # endregion Select

    # region Status

    @app_commands.command(
        name='status',
        description='Zeigt den Status deiner Kalender-Verknüpfung.'
    )
    @app_commands.checks.has_role('Lehrer')
    async def status(self, interaction: discord.Interaction):
        db_cal = TeacherCalendar(interaction.guild.id, interaction.user.id)
        lines = [
            f"Microsoft-Anbindung konfiguriert: {'ja' if msgraph.is_configured() else 'nein'}",
            f"Konto verknüpft: {'ja' if db_cal.is_linked else 'nein'}",
            f"Kalender: {db_cal.calendar_name or 'nicht ausgewählt'}",
            f"Zuletzt vorbereitet: {db_cal.last_prepared_date or 'noch nie'}",
            f'Tägliche Vorbereitung: {NIGHTLY_PREP_TIME} Uhr (Europe/Berlin)'
            + ('' if db_cal.is_ready else ': ohne Kalender werden alle Schüler-Channels archiviert'),
        ]
        await env.send_safe_response(interaction, '**Kalender-Status**\n' + '\n'.join(f'- {l}' for l in lines), ephemeral=True)

    @status.error
    async def status_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        await env.handle_app_command_error(
            interaction, error, command_name='calendar status', reqired_role='Lehrer'
        )

    # endregion Status

    # region Disconnect

    @app_commands.command(
        name='disconnect',
        description='Trennt die Kalender-Verknüpfung.'
    )
    @app_commands.checks.has_role('Lehrer')
    async def disconnect(self, interaction: discord.Interaction):
        TeacherCalendar(interaction.guild.id, interaction.user.id).delete()
        _calendar_cache.pop((interaction.guild.id, interaction.user.id), None)
        await env.send_safe_response(
            interaction,
            env.success_response(
                'Kalender-Verknüpfung getrennt. Ab jetzt werden nachts alle deine Schüler-Channels archiviert; '
                'sie kommen zurück, sobald ein Schüler schreibt oder die Lounge betritt.'),
            ephemeral=True
        )

    @disconnect.error
    async def disconnect_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        await env.handle_app_command_error(
            interaction, error, command_name='calendar disconnect', reqired_role='Lehrer'
        )

    # endregion Disconnect

    # region Preview / Prepare

    async def _run_prep(self, interaction: discord.Interaction, dry_run: bool):
        _require_ready(interaction)
        await interaction.response.defer(thinking=True, ephemeral=True)
        today = datetime.now(prep.BERLIN).date()
        try:
            result = await prep.prepare_teacher(interaction.guild, interaction.user.id, today, dry_run=dry_run)
        except (msgraph.GraphError, msgraph.GraphAuthError, msgraph.GraphNotConfiguredError) as e:
            _raise_graph_error(e)
        await interaction.followup.send(prep.format_summary(result, dry_run=dry_run), ephemeral=True)

    @app_commands.command(
        name='preview',
        description='Zeigt, welche Schüler heute verschoben würden (ohne etwas zu verschieben).'
    )
    @app_commands.checks.has_role('Lehrer')
    async def preview(self, interaction: discord.Interaction):
        await self._run_prep(interaction, dry_run=True)

    @preview.error
    async def preview_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        await env.handle_app_command_error(
            interaction, error, command_name='calendar preview', reqired_role='Lehrer'
        )

    @app_commands.command(
        name='prepare-now',
        description='Führt die Tagesvorbereitung jetzt sofort aus.'
    )
    @app_commands.checks.has_role('Lehrer')
    async def prepare_now(self, interaction: discord.Interaction):
        await self._run_prep(interaction, dry_run=False)

    @prepare_now.error
    async def prepare_now_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        await env.handle_app_command_error(
            interaction, error, command_name='calendar prepare-now', reqired_role='Lehrer'
        )

    # endregion Preview / Prepare


async def setup(bot):
    bot.tree.add_command(
        CalendarGroup(
            name='calendar',
            description='Kalender-Verknüpfung für die automatische Tagesvorbereitung'
        )
    )
    print('[Group] CalendarGroup loaded')
