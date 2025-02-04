import discord
from discord import app_commands
from discord.ext import commands

import Coordination.student as student

from Utils.errors import CodeError, UsageError
from Utils.logging import log
from Utils.msg import *


class StudentCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'[COG] {self.__cog_name__} is ready')

    @app_commands.command(
        name='assign_student',
        description="Registriert einen neuen Schüler."
    )
    @app_commands.checks.has_role('Lehrer')
    async def assign_student(self, interaction: discord.Interaction, member: discord.Member, student_name: str, silent: bool = False):
        await student.assign_student(interaction, member, student_name, silent)
        await safe_respond(interaction, success_msg(f"Schüler {member.mention} registriert"))

    @assign_student.error
    async def assign_student_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        await self.__handle_app_command_error(interaction, error, 'assign_student')

    @app_commands.command(
        name='unassign_student',
        description="Entfernt einen registrierten Schüler."
    )
    @app_commands.checks.has_role('Lehrer')
    async def unassign_student(self, interaction: discord.Interaction, member: discord.Member):
        await student.unassign_student(interaction, member)
        await safe_respond(interaction, success_msg(f"Schüler {member.mention} abgemeldet"))

    @unassign_student.error
    async def unassign_student_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        await self.__handle_app_command_error(interaction, error, 'unassign_student')

    @app_commands.command(
        name='stash-student',
        description='Verschiebt einen Schüler ins Archiv'
    )
    @app_commands.checks.has_role('Lehrer')
    async def stash_student(self, interaction: discord.Interaction, member: discord.Member):
        await student.stash_student(interaction, member)
        await safe_respond(interaction, success_msg(f"Schüler {member.mention} archiviert"))

    @stash_student.error
    async def stash_student_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        await self.__handle_app_command_error(interaction, error, 'stash-student')

    @app_commands.command(
        name='pop-student',
        description='Holt einen Schüler aus dem Archiv'
    )
    @app_commands.checks.has_role('Lehrer')
    async def pop_student(self, interaction: discord.Interaction, member: discord.Member):
        await student.pop_student(interaction, member)
        await safe_respond(interaction, success_msg(f"Schüler {member.mention} aus dem Archiv geholt"))

    @pop_student.error
    async def pop_student_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        await self.__handle_app_command_error(interaction, error, 'pop-student')

    async def __handle_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError, command_name: str):
        msg = self.__create_app_command_error_msg(error)
        if interaction.guild and not isinstance(error, UsageError) and not isinstance(error, app_commands.MissingRole):
            await log(interaction.guild, msg, details={'Command': command_name, 'Used by': f'{interaction.user.mention}'})
        await safe_respond(interaction, msg, ephemeral=True)

    def __create_app_command_error_msg(self, error: app_commands.AppCommandError) -> str:
        match error:
            case app_commands.MissingRole():
                return error_msg("Du musst die Rolle 'Lehrer' haben, um diesen Befehl zu benutzen.")
            case CodeError():
                return error_msg("Ein interner Fehler ist aufgetreten.", error=error)
            case UsageError():
                return error_msg(str(error))
            case _:
                return error_msg("Ein unbekannter Fehler ist aufgetreten.", error=error)


async def setup(bot):
    await bot.add_cog(StudentCog(bot))
