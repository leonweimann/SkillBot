import discord
from discord import app_commands
from discord.ext import commands

import Coordination.teacher as teacher
import Utils.environment as env


class TeacherCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'[COG] {self.__cog_name__} is ready')

    # region Assignments

    @app_commands.command(
        name='assign-teacher',
        description="Registriert einen neuen Lehrer."
    )
    @app_commands.checks.has_role('Admin')
    async def assign_teacher(self, interaction: discord.Interaction, member: discord.Member, teacher_name: str, subject: str | None = None, phonenumber: str | None = None, availability: str | None = None):
        await teacher.assign_teacher(interaction, member, teacher_name, subject, phonenumber, availability)
        await env.send_safe_response(interaction, env.success_response(f"Lehrer {member.mention} registriert"))

    @assign_teacher.error
    async def assign_teacher_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        await env.handle_app_command_error(interaction, error, 'assign_teacher', 'Admin')

    @app_commands.command(
        name='unassign-teacher',
        description="Entfernt einen registrierten Lehrer."
    )
    @app_commands.checks.has_role('Admin')
    async def unassign_teacher(self, interaction: discord.Interaction, member: discord.Member):
        await teacher.unassign_teacher(interaction, member)
        await env.send_safe_response(interaction, env.success_response(f"Lehrer {member.mention} abgemeldet"))

    @unassign_teacher.error
    async def unassign_teacher_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        await env.handle_app_command_error(interaction, error, 'unassign_teacher', 'Admin')

    # endregion

    # reagion Sort Channels

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        await teacher.sort_channels(channel)

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
        if before.name != after.name or before.category != after.category:  # Without this sorting would be infinite
            await teacher.sort_channels(after)

    # endregion


async def setup(bot):
    await bot.add_cog(TeacherCog(bot))
