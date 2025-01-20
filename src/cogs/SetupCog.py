import discord
from discord import app_commands
from discord.ext import commands

from Utils.errors import UsageError
from Utils.msg import error_msg, success_msg
from Utils.setup import setup_server as _setup_server


class SetupCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"[COG] {self.__cog_name__} is ready")

    @app_commands.command(
        name="setup-server",
        description="Initialisiert den Server für die Nutzung des Bots."
    )
    async def setup_server(self, interaction: discord.Interaction):
        if interaction.guild is None:
            raise UsageError("Dieser Befehl kann nur in einem Server verwendet werden.")

        if interaction.guild.owner_id is None:
            raise UsageError("Der Server hat keinen Besitzer.")

        if interaction.guild.owner_id != interaction.user.id:
            raise app_commands.MissingRole('Du musst der Server-Besitzer sein, um den Server zu als Nachhilfe Server zu initialisieren.')

        await interaction.response.defer()

        await _setup_server(interaction.guild)

        await interaction.followup.send(success_msg("Der Server wurde erfolgreich für die Nutzung des Bots konfiguriert."))

    @setup_server.error
    async def setup_server_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        match error:
            case app_commands.MissingRole():
                await interaction.followup.send(error_msg("Du musst der Server-Besitzer sein, um den Server zu als Nachhilfe Server zu initialisieren."), ephemeral=True)
            case UsageError():
                await interaction.followup.send(error_msg(str(error)), ephemeral=True)
            case _:
                await interaction.followup.send(error_msg("Ein unbekannter Fehler ist aufgetreten.", error), ephemeral=True)


async def setup(bot):
    await bot.add_cog(SetupCog(bot))
