import discord
from discord import app_commands
from discord.ext import commands

from utils import error_msg, success_msg


class TeacherCoordinator(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'[COG] {self.__cog_name__} is ready')

    @app_commands.command(name='assign_teacher', description="Registriert einen neuen Lehrer.")
    @app_commands.checks.has_role('Admin')
    async def assign_teacher(self, interaction: discord.Interaction, member: discord.User, teacher_name: str):
        await interaction.response.send_message(await self.__assign_teacher(interaction, member, teacher_name))

    @assign_teacher.error
    async def assign_teacher_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        match error:
            case app_commands.MissingRole():
                await interaction.response.send_message(error_msg("Du musst die Rolle 'Admin' haben, um diesen Befehl zu benutzen.", code_issue=False), ephemeral=True)
            case _:
                await interaction.response.send_message(error_msg("Ein interner Fehler ist aufgetreten."), ephemeral=True)

    @app_commands.command(name='unassign_teacher', description="Entfernt einen registrierten Lehrer.")
    @app_commands.checks.has_role('Admin')
    async def unassign_teacher(self, interaction: discord.Interaction, member: discord.User):
        await interaction.response.send_message(await self.__unasign_teacher(interaction, member))

    @unassign_teacher.error
    async def unassign_teacher_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        match error:
            case app_commands.MissingRole():
                await interaction.response.send_message(error_msg("Du musst die Rolle 'Admin' haben, um diesen Befehl zu benutzen.", code_issue=False), ephemeral=True)
            case _:
                await interaction.response.send_message(error_msg("Ein interner Fehler ist aufgetreten."), ephemeral=True)

    async def __assign_teacher(self, interaction: discord.Interaction, member: discord.User, teacher_name: str) -> str:
        if interaction.guild is None:
            return error_msg("Guild is None")

        teacher = interaction.guild.get_member(member.id)
        if teacher is None:
            return error_msg("Teacher is not a member")

        teacher_role = discord.utils.get(interaction.guild.roles, name='Lehrer')
        if teacher_role is None:
            return error_msg("Teacher role not found")

        # Check if teacher is already registered
        if teacher_role in teacher.roles:
            return error_msg(f"{teacher.mention} ist bereits registriert")

        # ---
        await teacher.add_roles(teacher_role)

        # ---
        new_nick = '🎓 ' + teacher_name
        await teacher.edit(nick=new_nick)

        # ---
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            teacher: discord.PermissionOverwrite(read_messages=True)
        }

        category = await interaction.guild.create_category(teacher.display_name, overwrites=overwrites)
        cmd_channel = await interaction.guild.create_text_channel('cmd', category=category, overwrites=overwrites)

        await cmd_channel.send(f"👋 Willkommen, {teacher.mention}! Hier kannst du Befehle ausführen.")

        return success_msg(f"Lehrer {teacher.mention} registriert")

    async def __unasign_teacher(self, interaction: discord.Interaction, member: discord.User) -> str:
        if interaction.guild is None:
            return error_msg("Guild is None")

        teacher = interaction.guild.get_member(member.id)
        if teacher is None:
            return error_msg("Teacher is not a member")

        teacher_role = discord.utils.get(interaction.guild.roles, name='Lehrer')
        if teacher_role is None:
            return error_msg("Teacher role not found")

        # Ensure teacher is assigned
        if teacher_role not in teacher.roles:
            return error_msg(f"{teacher.mention} ist kein registrierter Lehrer")

        irregular_circurstances_msgs = []

        # ---
        category = discord.utils.get(interaction.guild.categories, name=teacher.display_name)
        if category is not None:
            for channel in category.channels:
                await channel.delete()
            await category.delete()
        else:
            irregular_circurstances_msgs.append(f'Teachers category not found: {teacher.display_name}')

            # ---
        await teacher.remove_roles(teacher_role)

        # ---
        await teacher.edit(nick=None)

        return success_msg(f"Lehrer {teacher.mention} abgemeldet. {' '.join(irregular_circurstances_msgs)}")


async def setup(bot):
    await bot.add_cog(TeacherCoordinator(bot))
