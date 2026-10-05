import asyncio
import discord
from discord.ext import commands, tasks
from datetime import date, datetime, time

from Coordination.daily_prep import BERLIN, format_summary, get_cmd_channel, prepare_teacher
from Utils import msgraph
from Utils.database import TeacherCalendar
from Utils.lwlogging import log


PREPARATION_TIME = time(4, 0, tzinfo=BERLIN)


class DailyPreparation(commands.Cog):
    """
    Prepares the categories of all teachers with a linked calendar every night at 04:00 Europe/Berlin.

    Students with an appointment today get their channel moved into the teacher's category, all other
    students of that teacher get archived. A summary is posted into the teacher's ``cmd`` channel.
    """

    def __init__(self, bot):
        self.bot = bot
        self.debug = False  # Set to True to enable debug mode
        self._run_lock = asyncio.Lock()  # Prevents the catch-up and the nightly loop from running concurrently
        # Failures already reported (guild, teacher, day): on_ready fires on every reconnect and retries
        # the catch-up, which must not spam the cmd/logs channels
        self._reported_failures: set[tuple[int, int, date]] = set()

    def _debug_print(self, message: str):
        if self.debug:
            print(f'[DEBUG] {self.__class__.__name__}: {message}')

    async def cog_unload(self):
        self.daily_preparation.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        """
        Event listener that runs when the bot is ready.
        Starts the daily_preparation task and catches up on a missed run of today.
        """
        print(f'[COG] {self.__class__.__name__} is ready')
        if not self.daily_preparation.is_running():
            self.daily_preparation.start()

        # Catch-up: the bot was offline at 04:00 (on_ready can fire multiple times on reconnects,
        # already prepared teachers are skipped)
        if datetime.now(BERLIN).time() >= time(4, 0):
            await self._run_all(skip_prepared_today=True)

    @tasks.loop(time=PREPARATION_TIME)
    async def daily_preparation(self):
        """
        Prepares all teachers with a linked calendar for today.
        This task is scheduled to run at 04:00 Europe/Berlin (DST-aware).
        """
        self._debug_print('Running daily_preparation task')
        # The nightly run always prepares, even if /calendar prepare-now ran after midnight
        await self._run_all(skip_prepared_today=False)
        self._debug_print('Finished daily_preparation loop.')

    @daily_preparation.before_loop
    async def before_daily_preparation(self):
        await self.bot.wait_until_ready()

    async def _run_all(self, skip_prepared_today: bool):
        """
        Runs the preparation for every guild and every ready teacher calendar.

        Args:
            skip_prepared_today (bool): Skip teachers already prepared today (catch-up), so repeated
                on_ready events never prepare a teacher twice.
        """
        if not msgraph.is_configured():
            self._debug_print('Microsoft Graph is not configured, skipping')
            return

        async with self._run_lock:
            today = datetime.now(BERLIN).date()
            for guild in self.bot.guilds:
                try:
                    calendars = TeacherCalendar.get_all(guild.id)
                except Exception as e:
                    await self._safe_log(guild, '[ERROR] Tagesvorbereitung: Kalender konnten nicht geladen werden', {'error': str(e)})
                    continue

                for db_cal in calendars:
                    if not db_cal.is_ready:
                        continue
                    if skip_prepared_today and db_cal.last_prepared_date == today.isoformat():
                        continue
                    try:
                        await self._prepare_and_report(guild, db_cal.teacher_id, today)
                    except Exception as e:  # Never let one teacher stop the others
                        if not self._first_report(guild.id, db_cal.teacher_id, today):
                            continue
                        await self._safe_log(
                            guild,
                            '[ERROR] Tagesvorbereitung fehlgeschlagen',
                            {'Lehrer': f'<@{db_cal.teacher_id}>', 'error': str(e)}
                        )

    async def _prepare_and_report(self, guild: discord.Guild, teacher_id: int, today: date):
        """Prepares one teacher and posts the result (or an error notice) into their cmd channel."""
        self._debug_print(f'Preparing teacher {teacher_id} in guild {guild.name}')

        if guild.get_member(teacher_id) is None:
            await self._safe_log(
                guild,
                'Tagesvorbereitung übersprungen: Lehrer ist nicht (mehr) auf dem Server',
                {'Lehrer': f'<@{teacher_id}>', 'ID': str(teacher_id)}
            )
            return

        cmd_channel = get_cmd_channel(guild, teacher_id)

        try:
            result = await prepare_teacher(guild, teacher_id, today)
        except msgraph.GraphAuthError as e:
            # on_ready fires on every reconnect and retries the catch-up: notify only once per day
            if not self._first_report(guild.id, teacher_id, today):
                return
            if cmd_channel:
                await cmd_channel.send(
                    f'⚠️ <@{teacher_id}> Die Kalender-Verbindung ist abgelaufen, deshalb wurde heute nichts '
                    'vorbereitet. Bitte verbinde deinen Kalender erneut mit `/calendar connect`.',
                    allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False)
                )
            await self._safe_log(
                guild,
                'Tagesvorbereitung: Kalender-Verbindung abgelaufen',
                {'Lehrer': f'<@{teacher_id}>', 'error': str(e)}
            )
            return

        if cmd_channel:
            try:
                await cmd_channel.send(format_summary(result, dry_run=False), allowed_mentions=discord.AllowedMentions.none())
            except discord.HTTPException as e:  # The preparation itself succeeded
                await self._safe_log(guild, 'Tagesvorbereitung durchgeführt, Zusammenfassung konnte nicht gesendet werden',
                                     {'Lehrer': f'<@{teacher_id}>', 'error': str(e)})
        else:
            await self._safe_log(
                guild,
                'Tagesvorbereitung durchgeführt, aber kein `cmd`-Channel für den Lehrer gefunden',
                {'Lehrer': f'<@{teacher_id}>'}
            )

    def _first_report(self, guild_id: int, teacher_id: int, day: date) -> bool:
        """Returns True only the first time a failure of this teacher is reported on that day."""
        key = (guild_id, teacher_id, day)
        if key in self._reported_failures:
            return False
        self._reported_failures.add(key)
        return True

    async def _safe_log(self, guild: discord.Guild, message: str, details: dict[str, str] = {}):
        try:
            await log(guild, message, details)
        except Exception as e:
            print(f'[{self.__class__.__name__}] Failed to log "{message}" in guild {guild.name}: {e}')


async def setup(bot):
    await bot.add_cog(DailyPreparation(bot))
