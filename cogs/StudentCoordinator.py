import discord
from discord import app_commands
from discord.ext import commands

from utils import error_msg, success_msg


class StudentCoordinator(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'[COG] {self.__cog_name__} is ready')

    @app_commands.command(name='assign_student', description="Registriert einen neuen Schüler.")
    @app_commands.checks.has_role('Lehrer')
    async def assign_student(self, interaction: discord.Interaction, member: discord.User, student_name: str):
        await interaction.response.send_message(await self.__assign_student(interaction, member, student_name))

    @assign_student.error
    async def assign_student_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        match error:
            case app_commands.MissingRole():
                await interaction.response.send_message(error_msg("Du musst die Rolle 'Lehrer' haben, um diesen Befehl zu benutzen.", code_issue=False), ephemeral=True)
            case _:
                await interaction.response.send_message(error_msg("Ein interner Fehler ist aufgetreten."), ephemeral=True)

    @app_commands.command(name='unassign_student', description="Entfernt einen registrierten Schüler.")
    @app_commands.checks.has_role('Lehrer')
    async def unassign_student(self, interaction: discord.Interaction, member: discord.User):
        await interaction.response.send_message(await self.__unasign_student(interaction, member))

    @unassign_student.error
    async def unassign_student_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        match error:
            case app_commands.MissingRole():
                await interaction.response.send_message(error_msg("Du musst die Rolle 'Lehrer' haben, um diesen Befehl zu benutzen.", code_issue=False), ephemeral=True)
            case _:
                await interaction.response.send_message(error_msg("Ein interner Fehler ist aufgetreten."), ephemeral=True)

    async def __assign_student(self, interaction: discord.Interaction, member: discord.User, student_name: str) -> str:
        if interaction.guild is None:
            return error_msg("Guild is None")

        teacher = interaction.guild.get_member(interaction.user.id)
        if teacher is None:
            return error_msg("Interaction user is not a member")

        student = interaction.guild.get_member(member.id)
        if student is None:
            return error_msg("Student is not a member")

        student_role = discord.utils.get(interaction.guild.roles, name='Schüler')
        if student_role is None:
            return error_msg("Student role not found")

        # Check if student is already registered
        if student_role in student.roles:
            return error_msg(f"{student.mention} ist bereits registrierter Schüler", code_issue=False)

        # ---

        await student.add_roles(student_role)
        await student.edit(nick=f'🎒 {student_name}')  # Make icons personalisable

        teachers_category = discord.utils.get(interaction.guild.categories, name=teacher.display_name)
        if teachers_category is None:
            return error_msg("Teachers category not found")

        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            student: discord.PermissionOverwrite(read_messages=True),
            teacher: discord.PermissionOverwrite(read_messages=True)
        }

        channel = await interaction.guild.create_text_channel(student_name, category=teachers_category, overwrites=overwrites)
        await channel.send(f"👋 Willkommen, {student.mention}! Hier kannst du mit deinem Lehrer {teacher.mention} kommunizieren")

        return success_msg(f"Schüler {student.mention} registriert")

    async def __unasign_student(self, interaction: discord.Interaction, member: discord.User) -> str:
        if interaction.guild is None:
            return error_msg("Guild is None")

        teacher = interaction.guild.get_member(interaction.user.id)
        if teacher is None:
            return error_msg("Interaction user is not a member")

        student = interaction.guild.get_member(member.id)
        if student is None:
            return error_msg("Student is not a member")

        student_role = discord.utils.get(interaction.guild.roles, name='Schüler')
        if student_role is None:
            return error_msg("Student role not found")

        # Ensure student is assigned
        if student_role not in student.roles:
            return error_msg(f"{student.mention} ist kein registrierter Schüler", code_issue=False)

        # ---
        teachers_category = discord.utils.get(interaction.guild.categories, name=teacher.display_name)
        if teachers_category is None:
            return error_msg("Teachers category not found")

        for channel in teachers_category.channels:
            if channel.name == student.display_name:
                await channel.delete()
                break

        await student.edit(nick=None)
        await student.remove_roles(student_role)

        return success_msg(f"Schüler {student.mention} abgemeldet")


async def setup(bot):
    await bot.add_cog(StudentCoordinator(bot))
