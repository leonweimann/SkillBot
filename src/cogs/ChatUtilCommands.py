import discord
from discord import app_commands
from discord.ext import commands

from Utils.msg import *


class ChatUtilCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'[COG] {self.__cog_name__} is ready')

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
                await interaction.followup.send(success_msg(f"{len(deleted_messages)} Nachrichten gelöscht."), ephemeral=True)
            case _:
                await interaction.response.send_message(error_msg('Dieser Befehl kann nur in Textkanälen verwendet werden.'), ephemeral=True)

    @clear.error
    async def clear_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        match error:
            case app_commands.MissingRole():
                await interaction.response.send_message(error_msg("Du musst die Rolle 'Admin' haben, um diesen Befehl zu benutzen."), ephemeral=True)
            case _:
                await interaction.response.send_message(error_msg("Ein unbekannter Fehler ist aufgetreten.", error), ephemeral=True)


async def setup(bot):
    await bot.add_cog(ChatUtilCommands(bot))
