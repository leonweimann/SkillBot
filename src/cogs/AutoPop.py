import discord
from discord.ext import commands

from Coordination.daily_prep import is_archived_category, pop_to_teacher
from Utils.database import TeacherStudentConnection
from Utils.lwlogging import log


class AutoPop(commands.Cog):
    """
    Moves an archived student channel back into the teacher's category as soon as someone
    other than the teacher writes into it.
    """

    def __init__(self, bot):
        self.bot = bot
        self.debug = False  # Set to True to enable debug mode

    def _debug_print(self, message: str):
        if self.debug:
            print(f'[DEBUG] {self.__class__.__name__}: {message}')

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
            self._debug_print(f'Error while auto-popping {channel.name}: {e}')
            try:
                await log(
                    guild,
                    f'[ERROR] Auto-Pop für {channel.mention} fehlgeschlagen',
                    {'error': str(e)}
                )
            except Exception as log_error:
                print(f'[{self.__class__.__name__}] Failed to log auto-pop error in guild {guild.name}: {log_error}')


async def setup(bot):
    await bot.add_cog(AutoPop(bot))
