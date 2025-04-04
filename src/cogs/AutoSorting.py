import discord
from discord.ext import commands, tasks
from discord import app_commands

import Utils.environment as env

from Coordination.sorting import channel_sorting_coordinator


class AutoSorting(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'[COG] {self.__cog_name__} is ready')

    def cog_unload(self):
        """
        This method is called when the cog is unloaded.
        It stops the auto_sort_channels task.
        """
        self.auto_sort_channels.stop()

    @tasks.loop(hours=1)
    async def auto_sort_channels(self):
        """
        Automatically sorts channels every hour.
        """
        for guild in self.bot.guilds:
            for category in guild.categories:
                await channel_sorting_coordinator.sort_channels_in_category(category)

    @auto_sort_channels.before_loop
    async def before_auto_sort_channels(self):
        await self.bot.wait_until_ready()

    @app_commands.command(
        name='do-auto-sort',
        description='Sorts the channels in the specified category.'
    )
    @app_commands.describe(
        category='The category to sort channels in.'
    )
    @app_commands.checks.has_role('Admin')
    async def do_auto_sort(self, interaction: discord.Interaction, category: discord.CategoryChannel):
        """
        Sorts the channels in the specified category.
        """
        if not channel_sorting_coordinator._is_allowed_category(category):
            await interaction.response.send_message(
                env.failure_response(f'Category {category.name} is not allowed to be sorted.')
            )
            return

        await interaction.response.defer(thinking=True)
        await channel_sorting_coordinator.sort_channels_in_category(category)
        await interaction.followup.send(
            env.success_response(f'Sorted channels in {category.name} ({category.id})')
        )

    @do_auto_sort.error
    async def do_auto_sort_error(self, interaction: discord.Interaction, error):
        await env.handle_app_command_error(
            interaction, error, 'do-auto-sort', 'Admin'
        )


async def setup(bot):
    await bot.add_cog(AutoSorting(bot))
