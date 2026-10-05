import discord
from discord.ext import commands

from Coordination.daily_prep import LOUNGE_CHANNEL_NAME, is_archived_category, pop_to_teacher, resolve_student_id
from Utils.database import TeacherStudentConnection
from Utils.lwlogging import log

def joined_lounge(before_channel, after_channel) -> bool:
    """
    Checks whether a voice state change is a join of the lounge.

    Args:
        before_channel: The voice channel before the change (``None`` if not connected).
        after_channel: The voice channel after the change (``None`` if not connected).

    Returns:
        bool: True only if the lounge was entered, False for leaving, other channels
        and state changes within the same channel (mute, deafen, stream, video).
    """
    if after_channel is None or after_channel.name != LOUNGE_CHANNEL_NAME:
        return False
    return before_channel is None or before_channel.id != after_channel.id


class AutoPop(commands.Cog):
    """
    Moves an archived student channel back into the teacher's category as soon as someone
    other than the teacher writes into it, or as soon as the student joins the lounge voice channel.
    """

    def __init__(self, bot):
        self.bot = bot
        self.debug = False  # Set to True to enable debug mode

    def _debug_print(self, message: str):
        if self.debug:
            print(f'[DEBUG] {self.__class__.__name__}: {message}')

    async def _log_error(self, guild: discord.Guild, subject: str, error: Exception):
        """Logs a failed auto-pop; never raises."""
        self._debug_print(f'Error while auto-popping {subject}: {error}')
        try:
            await log(guild, f'[ERROR] Auto-Pop für {subject} fehlgeschlagen', {'error': str(error)})
        except Exception as log_error:
            print(f'[{self.__class__.__name__}] Failed to log auto-pop error in guild {guild.name}: {log_error}')

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'[COG] {self.__class__.__name__} is ready')

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """
        Pops the channel of the message back into the teacher's category if it is archived.

        Ignores DMs, bots, webhooks, non-student channels and messages of the teacher.
        Never raises; errors are logged.
        """
        guild = message.guild
        if guild is None or message.author.bot or message.webhook_id is not None:
            return

        channel = message.channel
        if isinstance(channel, discord.Thread):  # A reply in a thread counts for its student channel
            channel = channel.parent
        if not isinstance(channel, discord.TextChannel):
            return

        try:
            # Cheap pre-check from the cache, before any further DB query or API call
            if not is_archived_category(guild, channel.category_id):
                return

            ts_con = TeacherStudentConnection.find_by_channel(guild.id, channel.id)
            if ts_con is None or message.author.id == ts_con.teacher_id:
                return

            if await pop_to_teacher(guild, ts_con):
                self._debug_print(f'Popped {channel.name} in guild {guild.name}')
                await log(
                    guild,
                    f'Auto-Pop: {channel.mention} wurde wegen einer Nachricht von {message.author.mention} in die Lehrer-Kategorie verschoben',
                    {'Lehrer': f'<@{ts_con.teacher_id}>', 'Channel': channel.name}
                )
        except Exception as e:
            await self._log_error(guild, channel.mention, e)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """
        Pops the archived student channel of a student into the teacher's category when the
        student joins the lounge voice channel.

        Sub-accounts are resolved to their main student. Ignores bots, state changes within
        a channel, other voice channels and members without a student channel (e.g. teachers).
        Never raises; errors are logged.
        """
        if member.bot or not joined_lounge(before.channel, after.channel):
            return

        guild = member.guild
        try:
            student_id = resolve_student_id(guild.id, member.id)
            ts_con = TeacherStudentConnection.find_by_student(guild.id, student_id)
            if ts_con is None:
                return

            # Cheap pre-check from the cache, before any further API call
            channel = guild.get_channel(ts_con.channel_id)
            if channel is None or not is_archived_category(guild, channel.category_id):
                return

            if await pop_to_teacher(guild, ts_con, reason='Auto-Pop: Lounge betreten'):
                self._debug_print(f'Popped {channel.name} in guild {guild.name}')
                await log(
                    guild,
                    f'Auto-Pop: {channel.mention} wurde verschoben, weil {member.mention} die Lounge betreten hat',
                    {'Lehrer': f'<@{ts_con.teacher_id}>', 'Channel': channel.name}
                )
        except Exception as e:
            await self._log_error(guild, member.mention, e)


async def setup(bot):
    await bot.add_cog(AutoPop(bot))
