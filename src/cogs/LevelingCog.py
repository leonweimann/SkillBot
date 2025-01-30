import discord
from discord import app_commands
from discord.ext import commands

from Utils.database import *
from Utils.logging import log
from Utils.msg import error_msg


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
        db_user = DBUser(member.id)
        if before.channel is None and after.channel is not None and after.channel.name == 'klassenzimmer':
            db_user.save_voice_channel_join(after.channel.id)
        elif before.channel is not None and before.channel.name == 'klassenzimmer' and after.channel != before.channel:
            db_user.transfer_hours_in_class_from_user_voice_channel_join()

    @app_commands.command(
        name='time',
        description="Gibt dem Benutzer die Gesamtzeit zurück, die er im 'klassenzimmer' verbracht hat.",
    )
    async def time(self, interaction: discord.Interaction, user: discord.Member | None = None):
        """
        Command that allows users to check the total time spent in the voice channel 'klassenzimmer'.
        """
        if interaction.guild is None:
            await interaction.response.send_message(error_msg('Dieser Befehl kann nur in einem Server verwendet werden.'), ephemeral=True)
            return

        if not user:
            if isinstance(interaction.user, discord.Member):
                user = interaction.user
            else:
                msg = error_msg('Ein Fehler beim Finden des Richtigen Nutzers ist aufgekommen.')
                await log(interaction.guild, msg, {'Used by': f'{interaction.user.mention}'})
                await interaction.response.send_message(msg, ephemeral=True)
                return

        db_user = DBUser(user.id)
        await interaction.response.send_message(f'{user.mention} hat insgesamt {db_user.hours_in_class} Stunden im "klassenzimmer" verbracht.', ephemeral=True)


async def setup(bot):
    await bot.add_cog(LevelingCog(bot))
