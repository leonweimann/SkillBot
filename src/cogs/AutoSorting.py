import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import time, timezone

import Utils.environment as env
from Utils.errors import CodeError
from Utils.logging import log

from Coordination.sorting import channel_sorting_coordinator


class AutoSorting(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.debug = False  # Set to True to enable debug mode

    def _debug_print(self, message: str):
        if self.debug:
            print(f"[DEBUG] AutoSorting: {message}")

    @tasks.loop(time=time(0, 0, tzinfo=timezone.utc))
    async def auto_sort_channels(self):
        """
        Automatically sorts all channels using the channel_sorting_coordinator.
        This task is scheduled to run at midnight UTC (2 AM German time).
        """
        for guild in self.bot.guilds:
            self._debug_print(f'Running auto_sort_channels for guild: {guild.name}')
            for category in guild.categories:
                try:
                    self._debug_print(f"Sorting category {category.name}")
                    await channel_sorting_coordinator.sort_channels_in_category(category)
                except Exception as e:
                    self._debug_print(f"Error sorting category {category.name}: {e}")
                    await log(
                        guild,
                        f"[ERROR] Failed to sort category {category.name} in guild {guild.name}",
                        {"error": str(e)}
                    )
        self._debug_print('Finished auto_sort_channels loop.')

    @app_commands.command(
        name='do-auto-sort',
        description='Sorts the channels in the specified category.'
    )
    @app_commands.describe(category='The category to sort channels in.')
    @app_commands.checks.has_role('Admin')
    async def do_auto_sort(self, interaction: discord.Interaction, category: discord.CategoryChannel):
        """
        Sorts the channels in the specified category.
        """
        if not interaction.guild:
            raise CodeError('This command can only be used in a guild.')

        if not channel_sorting_coordinator._is_allowed_category(category):
            await interaction.response.send_message(
                env.failure_response(f'Category {category.name} is not allowed to be sorted.')
            )
            await log(interaction.guild, '[COMMAND] do-auto-sort: Category not allowed', {"category": category.name})
            return

        # Check bot permissions
        if not category.permissions_for(interaction.guild.me).manage_channels:
            await interaction.response.send_message(
                env.failure_response(f'I do not have permission to manage channels in {category.name}.')
            )
            await log(interaction.guild, '[COMMAND] do-auto-sort: Missing permissions', {"category": category.name})
            return

        await interaction.response.defer(thinking=True)
        try:
            await channel_sorting_coordinator.sort_channels_in_category(category)
            await interaction.followup.send(
                env.success_response(f'Sorted channels in {category.name} ({category.id})')
            )
            self._debug_print(f'Successfully sorted channels in category {category.name} ({category.id})')
        except Exception as e:
            self._debug_print(f'Error sorting channels in category {category.name}: {e}')
            await log(
                interaction.guild,
                '[COMMAND] do-auto-sort: Failed to sort channels',
                {"category": category.name, "error": str(e)}
            )
            await interaction.followup.send(
                env.failure_response(f'Failed to sort channels in {category.name}. Please try again later.')
            )

    @do_auto_sort.error
    async def do_auto_sort_error(self, interaction: discord.Interaction, error):
        if interaction.guild:
            await log(interaction.guild, '[COMMAND] do-auto-sort: Error occurred', {"error": str(error)})
        self._debug_print(f'Error in do_auto_sort command: {error}')
        await env.handle_app_command_error(interaction, error, 'do-auto-sort', 'Admin')

    # @app_commands.command(
    #     name='toggle-auto-sort',
    #     description='Toggles the auto-sorting task on or off.'
    # )
    # @app_commands.checks.has_role('Admin')
    # async def toggle_auto_sort(self, interaction: discord.Interaction):
    #     """
    #     Toggles the auto-sorting task on or off.
    #     """
    #     if not interaction.guild:
    #         raise CodeError('This command can only be used in a guild.')

    #     if self.auto_sort_channels.is_running():
    #         self.auto_sort_channels.cancel()
    #         await interaction.response.send_message(env.success_response('Auto-sorting has been stopped.'))
    #         self._debug_print('Auto-sorting has been stopped.')
    #         await log(interaction.guild, '[COMMAND] toggle-auto-sort: Auto-sorting has been stopped.')
    #     else:
    #         self.auto_sort_channels.start()
    #         await interaction.response.send_message(env.success_response('Auto-sorting has been started.'))
    #         self._debug_print('Auto-sorting has been started.')
    #         await log(interaction.guild, '[COMMAND] toggle-auto-sort: Auto-sorting has been started.')

    # @toggle_auto_sort.error
    # async def toggle_auto_sort_error(self, interaction: discord.Interaction, error):
    #     if interaction.guild:
    #         await log(interaction.guild, '[COMMAND] toggle-auto-sort: Error occurred', {"error": str(error)})
    #     self._debug_print(f'Error in toggle_auto_sort command: {error}')
    #     await env.handle_app_command_error(interaction, error, 'toggle-auto-sort', 'Admin')


async def setup(bot):
    await bot.add_cog(AutoSorting(bot))
