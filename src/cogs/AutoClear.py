import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import time, timezone

import Utils.environment as env


class AutoClear(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.debug = False  # Set to True to enable debug mode

    def _debug_msg(self, msg: str):
        if self.debug:
            print(f'[DEBUG] {self.__class__.__name__}: {msg}')

    @commands.Cog.listener()
    async def on_ready(self):
        """
        Event listener that runs when the bot is ready.
        Starts the auto_clear task.
        """
        print(f'[COG] {self.__class__.__name__} is ready')
        self.auto_clear.start()

    @tasks.loop(time=time(22, 0, tzinfo=timezone.utc))
    async def auto_clear(self):
        self._debug_msg('Running auto_clear task')
        await self._auto_clear()
        self._debug_msg('Finished auto_clear loop.')

    async def _auto_clear(self):
        for guild in self.bot.guilds:
            self._debug_msg(f'Running auto_clear for guild: {guild.name}')
            for channel in guild.text_channels:
                if channel.name == 'cmd':
                    self._debug_msg(f'Found cmd channel: {channel.category.name} -> {channel.name}')
                    try:
                        await channel.purge()
                    except discord.Forbidden:
                        self._debug_msg(f'No permission to purge channel: {channel.name}')
                    except discord.HTTPException as e:
                        self._debug_msg(f'HTTPException while purging channel {channel.name}: {e}')
                    except Exception as e:
                        self._debug_msg(f'Error while purging channel {channel.name}: {e}')
                        await env.log(
                            guild,
                            f"[ERROR] Failed to clear channel {channel.name} in guild {guild.name}",
                            {"error": str(e)}
                        )

    @app_commands.command(
        name='do-auto-clear',
        description='Executes the auto clear task manually.'
    )
    @app_commands.checks.has_role('Admin')
    async def do_auto_clear(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        await self._auto_clear()

    @do_auto_clear.error
    async def do_auto_clear_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        await env.handle_app_command_error(interaction, error, 'do-auto-clear', 'Admin')


async def setup(bot):
    await bot.add_cog(AutoClear(bot))
