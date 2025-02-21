import discord
from discord import app_commands
from discord.ext import commands

import Coordination.teacher as teacher

import Utils.environment as env
from Utils.errors import *
from Utils.logging import log


class TeacherCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'[COG] {self.__cog_name__} is ready')

    @app_commands.command(
        name='assign-teacher',
        description="Registriert einen neuen Lehrer."
    )
    @app_commands.checks.has_role('Admin')
    async def assign_teacher(self, interaction: discord.Interaction, member: discord.Member, teacher_name: str):
        await teacher.assign_teacher(interaction, member, teacher_name)
        await env.send_safe_response(interaction, env.success_response(f"Lehrer {member.mention} registriert"))

    @assign_teacher.error
    async def assign_teacher_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        msg = self.__create_app_command_error_msg(error)

        if interaction.guild and not isinstance(error, UsageError) and not isinstance(error, app_commands.MissingRole):
            await log(interaction.guild, msg, details={'Command': 'clear', 'Used by': f'{interaction.user.mention}'})

        await env.send_safe_response(interaction, msg, ephemeral=True)

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
        msg = self.__create_app_command_error_msg(error)

        if interaction.guild and not isinstance(error, UsageError) and not isinstance(error, app_commands.MissingRole):
            await log(interaction.guild, msg, details={'Command': 'clear', 'Used by': f'{interaction.user.mention}'})

        await env.send_safe_response(interaction, msg, ephemeral=True)

    def __create_app_command_error_msg(self, error: app_commands.AppCommandError) -> str:
        match error:
            case app_commands.MissingRole():
                return env.failure_response("Du musst die Rolle 'Admin' haben, um diesen Befehl zu benutzen.")
            case CodeError():
                return env.failure_response("Ein interner Fehler ist aufgetreten.", error=error)
            case UsageError():
                return env.failure_response(str(error))
            case _:
                return env.failure_response("Ein unbekannter Fehler ist aufgetreten.", error=error)


async def setup(bot):
    await bot.add_cog(TeacherCog(bot))
