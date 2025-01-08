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


async def setup(bot):
    bot.add_cog(StudentCoordinator(bot))


# async def __registerStudent(interaction: discord.Interaction, student: discord.Member, student_name: str):
#     teacher = interaction.user
#     if not isinstance(teacher, discord.Member):
#         raise ValueError("teacher is no member")

#     guild = unwrapped(interaction.guild)
#     category = unwrapped(discord.utils.get(guild.categories, name=teacher.display_name))

#     # No exceptions from here on

#     # Update server presence
#     await student.edit(nick=student_name)

#     # Create a new channel for the student
#     overwrites = {
#         guild.default_role: discord.PermissionOverwrite(read_messages=False),
#         student: discord.PermissionOverwrite(read_messages=True),
#         teacher: discord.PermissionOverwrite(read_messages=True)
#     }

#     channel = await guild.create_text_channel(student_name, category=category, overwrites=overwrites)
#     await channel.send(f"👋 Willkommen, {student.mention}! Hier kannst du mit deinem Lehrer {teacher.mention} kommunizieren")
