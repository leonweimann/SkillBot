import discord
from discord import app_commands
from discord.ext import commands

import Coordination.student as student
import Utils.environment as env


class StudentCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'[COG] {self.__cog_name__} is ready')

    # region Assignments

    @app_commands.command(
        name='assign-student',
        description="Registriert einen neuen Schüler."
    )
    @app_commands.checks.has_role('Lehrer')
    async def assign_student(self, interaction: discord.Interaction, member: discord.Member, student_name: str, silent: bool = False):
        await student.assign_student(interaction, member, student_name, silent)
        await env.send_safe_response(interaction, env.success_response(f"Schüler {member.mention} registriert"))

    @assign_student.error
    async def assign_student_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        await env.handle_app_command_error(interaction, error, 'assign_student', 'Lehrer')

    @app_commands.command(
        name='unassign-student',
        description="Entfernt einen registrierten Schüler."
    )
    @app_commands.checks.has_role('Lehrer')
    async def unassign_student(self, interaction: discord.Interaction, member: discord.Member):
        await student.unassign_student(interaction, member)
        await env.send_safe_response(interaction, env.success_response(f"Schüler {member.mention} abgemeldet"))

    @unassign_student.error
    async def unassign_student_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        await env.handle_app_command_error(interaction, error, 'unassign_student', 'Lehrer')

    # endregion

    # region Stash

    @app_commands.command(
        name='stash-student',
        description='Verschiebt einen Schüler ins Archiv'
    )
    @app_commands.checks.has_role('Lehrer')
    async def stash_student(self, interaction: discord.Interaction, member: discord.Member):
        await student.stash_student(interaction, member)
        await env.send_safe_response(interaction, env.success_response(f"Schüler {member.mention} archiviert"))

    @stash_student.error
    async def stash_student_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        await env.handle_app_command_error(interaction, error, 'stash-student', 'Lehrer')

    @app_commands.command(
        name='pop-student',
        description='Holt einen Schüler aus dem Archiv'
    )
    @app_commands.checks.has_role('Lehrer')
    async def pop_student(self, interaction: discord.Interaction, member: discord.Member):
        await student.pop_student(interaction, member)
        await env.send_safe_response(interaction, env.success_response(f"Schüler {member.mention} aus dem Archiv geholt"))

    @pop_student.error
    async def pop_student_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        await env.handle_app_command_error(interaction, error, 'pop-student', 'Lehrer')

    # endregion

    # region Connections

    @app_commands.command(
        name='connect-student',
        description='Verbindet einen weiteren Account mit einem Schüler'
    )
    @app_commands.checks.has_role('Lehrer')
    async def connect_student(self, interaction: discord.Interaction, member: discord.Member, other_account: discord.Member):
        await student.connect_student(interaction, member, other_account)
        await env.send_safe_response(interaction, env.success_response(f"Account {other_account.mention} mit Schüler {member.mention} verbunden"))

    @connect_student.error
    async def connect_student_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        await env.handle_app_command_error(interaction, error, 'connect-student', 'Lehrer')

    @app_commands.command(
        name='disconnect-student',
        description='Trennt einen weiteren Account von einem Schüler'
    )
    @app_commands.checks.has_role('Lehrer')
    async def disconnect_student(self, interaction: discord.Interaction, member: discord.Member, other_account: discord.Member):
        await student.disconnect_student(interaction, member, other_account)
        await env.send_safe_response(interaction, env.success_response(f"Account {other_account.mention} von Schüler {member.mention} getrennt"))

    @disconnect_student.error
    async def disconnect_student_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        await env.handle_app_command_error(interaction, error, 'disconnect-student', 'Lehrer')

    # endregion


async def setup(bot):
    await bot.add_cog(StudentCog(bot))
