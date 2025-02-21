import discord
from discord import app_commands
from discord.ext import commands

import Coordination.setup as stp

import Utils.environment as env
from Utils.errors import *
from Utils.logging import log
# from Utils.msg import safe_respond


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

        await stp.setup_server(interaction.guild)

        await interaction.followup.send(env.success_response("Der Server wurde erfolgreich für die Nutzung des Bots konfiguriert."))

    @setup_server.error
    async def setup_server_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        match error:
            case app_commands.MissingRole():
                msg = env.failure_response("Du musst der Server-Besitzer sein, um den Server zu als Nachhilfe Server zu initialisieren.")
            case UsageError():
                msg = env.failure_response(str(error))
            case _:
                msg = env.failure_response("Ein unbekannter Fehler ist aufgetreten.", error)

        if interaction.guild and not isinstance(error, UsageError):
            await log(interaction.guild, msg)

        await env.send_safe_response(interaction, msg, ephemeral=True)


async def setup(bot):
    await bot.add_cog(SetupCog(bot))
