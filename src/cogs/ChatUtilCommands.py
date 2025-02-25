import discord
from discord import app_commands
from discord.ext import commands

import Utils.environment as env


class ChatUtilCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'[COG] {self.__cog_name__} is ready')

    # region Clear Command

    @app_commands.command(
        name='clear',
        description="Löscht eine bestimmte Anzahl an Nachrichten."
    )
    @app_commands.checks.has_role('Admin')
    async def clear(self, interaction: discord.Interaction):
        match interaction.channel:
            case discord.TextChannel():
                await interaction.response.defer(ephemeral=True)
                deleted_messages = await interaction.channel.purge()
                await interaction.followup.send(env.success_response(f"{len(deleted_messages)} Nachrichten gelöscht."), ephemeral=True)
            case _:
                await interaction.response.send_message(env.failure_response('Dieser Befehl kann nur in Textkanälen verwendet werden.'), ephemeral=True)

    @clear.error
    async def clear_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        await env.handle_app_command_error(interaction, error, 'clear', 'Admin')

    # endregion


async def setup(bot):
    await bot.add_cog(ChatUtilCommands(bot))
