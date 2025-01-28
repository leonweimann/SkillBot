import discord
from discord import app_commands
from discord.ext import commands

from Coordination.teacher import assign_teacher as _assign_teacher, unassign_teacher as _unassign_teacher

from Utils.errors import *
from Utils.msg import *


class TeacherCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'[COG] {self.__cog_name__} is ready')

    @app_commands.command(
        name='assign_teacher',
        description="Registriert einen neuen Lehrer."
    )
    @app_commands.checks.has_role('Admin')
    async def assign_teacher(self, interaction: discord.Interaction, member: discord.Member, teacher_name: str):
        await _assign_teacher(interaction, member, teacher_name)
        await save_respond(interaction, success_msg(f"Lehrer {member.mention} registriert"))

    @assign_teacher.error
    async def assign_teacher_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        await save_respond(interaction, self.__create_app_command_error_msg(error), ephemeral=True)

    @app_commands.command(
        name='unassign_teacher',
        description="Entfernt einen registrierten Lehrer."
    )
    @app_commands.checks.has_role('Admin')
    async def unassign_teacher(self, interaction: discord.Interaction, member: discord.Member):
        await _unassign_teacher(interaction, member)
        await save_respond(interaction, success_msg(f"Lehrer {member.mention} abgemeldet"))

    @unassign_teacher.error
    async def unassign_teacher_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        await save_respond(interaction, self.__create_app_command_error_msg(error), ephemeral=True)

    def __create_app_command_error_msg(self, error: app_commands.AppCommandError) -> str:
        match error:
            case app_commands.MissingRole():
                return error_msg("Du musst die Rolle 'Admin' haben, um diesen Befehl zu benutzen.")
            case CodeError():
                return error_msg("Ein interner Fehler ist aufgetreten.", error=error)
            case UsageError():
                return error_msg(str(error))
            case _:
                return error_msg("Ein unbekannter Fehler ist aufgetreten.", error=error)


async def setup(bot):
    await bot.add_cog(TeacherCog(bot))
