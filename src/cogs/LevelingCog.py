import discord
from discord import app_commands
from discord.ext import commands

from Utils.database import *
import Utils.environment as env
from Utils.lwlogging import log


class LevelingCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'[COG] {self.__cog_name__} is ready')

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """
        Event listener that triggers when a member's voice state changes.

        This function handles the following scenarios:
        1. When a member joins the voice channel named 'klassenzimmer', it saves the channel ID.
        2. When a member leaves the voice channel named 'klassenzimmer', it transfers the hours
        spent in the channel to the users hours_in_class property.
        """
        if before.channel is None and after.channel is not None and after.channel.name == 'klassenzimmer':
            UserVoiceChannelJoin(member.guild.id, member.id, after.channel.id).save()
        elif before.channel is not None and before.channel.name == 'klassenzimmer' and after.channel != before.channel:
            UserVoiceChannelJoin.transfer_hours(member.guild.id, member.id)

    @app_commands.command(
        name='time',
        description="Gibt dem Benutzer die Gesamtzeit zurück, die er im 'klassenzimmer' verbracht hat.",
    )
    async def time(self, interaction: discord.Interaction, user: discord.Member | None = None):
        """
        Command that allows users to check the total time spent in the voice channel 'klassenzimmer'.
        """
        if interaction.guild is None:
            await interaction.response.send_message(env.failure_response('Dieser Befehl kann nur in einem Server verwendet werden.'), ephemeral=True)
            return

        if not user:
            if isinstance(interaction.user, discord.Member):
                user = interaction.user
            else:
                msg = env.failure_response('Ein Fehler beim Finden des Richtigen Nutzers ist aufgekommen.')
                await log(interaction.guild, msg, {'Used by': f'{interaction.user.mention}'})
                await interaction.response.send_message(msg, ephemeral=True)
                return

        db_user = User(interaction.guild.id, user.id)
        await interaction.response.send_message(f'{user.mention} hat insgesamt {db_user.hours_in_class} Stunden im "klassenzimmer" verbracht.')

    @app_commands.command(
        name='set_hours',
        description="Setzt die Gesamtzeit, die ein Benutzer im 'klassenzimmer' verbracht hat."
    )
    @commands.has_role('Admin')
    async def set_hours(self, interaction: discord.Interaction, user: discord.Member, hours: float):
        """
        Command that allows users to set the total time spent in the voice channel 'klassenzimmer'.
        """
        if interaction.guild is None:
            await interaction.response.send_message(env.failure_response('Dieser Befehl kann nur in einem Server verwendet werden.'), ephemeral=True)
            return

        db_user = User(interaction.guild.id, user.id)
        db_user.edit(hours_in_class=hours)
        await interaction.response.send_message(f'{user.mention} hat jetzt insgesamt {db_user.hours_in_class} Stunden im "klassenzimmer" verbracht.')

    @set_hours.error
    async def set_hours_error(self, interaction, error):
        if isinstance(error, commands.MissingRole):
            await interaction.response.send_message(env.failure_response('Du hast nicht die Berechtigung, diesen Befehl auszuführen.'), ephemeral=True)
        else:
            msg = env.failure_response('Ein Fehler ist aufgetreten.', error)
            await log(interaction.guild, msg, {'Used by': f'{interaction.user.mention}'})
            await interaction.response.send_message(msg, ephemeral=True)


async def setup(bot):
    print(f'⚠️ [COG] {LevelingCog.__name__} is deactivated.')
    return
    await bot.add_cog(LevelingCog(bot))
