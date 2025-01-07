from enum import Enum
from dotenv import load_dotenv
import os
import discord
from discord import app_commands


load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
if TOKEN is None:
    raise ValueError("DISCORD_TOKEN environment variable not set")

GUILD_ID = os.getenv('GUILD_ID')
if GUILD_ID is None:
    raise ValueError("GUILD_ID environment variable not set")
elif not GUILD_ID.isdigit():
    raise ValueError("GUILD_ID must be a valid integer")
GUILD_ID = int(GUILD_ID)


MY_GUILD = discord.Object(id=GUILD_ID)


class MyClient(discord.Client):
    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        self.tree.copy_global_to(guild=MY_GUILD)
        await self.tree.sync(guild=MY_GUILD)


intents = discord.Intents.default()
client = MyClient(intents=intents)


@client.event
async def on_ready():
    print(f'Logged in as {client.user}')
    print('------')


@client.tree.command()
async def register(interaction: discord.Interaction, role: discord.Role, member: discord.Member, member_name: str):
    """Registers a new member"""
    required_roles: dict[str, list[str]] = {'Lehrer': ['Lehrer'], 'Schüler': ['Lehrer']}
    # required_roles: dict[str, list[str]] = {'Lehrer': ['Admin'], 'Schüler': ['Admin', 'Lehrer']}

    if (required_role := required_roles.get(role.name)) is None:
        await interaction.response.send_message(f"⚠️ Die Rolle {role.mention} kann nicht registriert werden.")
        return

    if not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message("⚠️ Interaktion ist ungültig.")
        return

    if not any(role.name in required_role for role in interaction.user.roles):
        await interaction.response.send_message("⛔ Du bist zur Nutzung dieses Befehls nicht berechtigt.")
        return

    if role in member.roles:
        await interaction.response.send_message(f"⚠️ {member.mention} ist bereits registriert.")
        return

    try:
        if role.name == 'Lehrer':
            await __registerTeacher(interaction, member, member_name)
        elif role.name == 'Schüler':
            await __registerStudent(interaction, member, member_name)

        await member.add_roles(role)
        await interaction.response.send_message(f"✅ {member.name} wurde erfolgreich registriert.")

    except ValueError as e:
        await interaction.response.send_message("⚠️ Fehler beim Registrieren: " + str(e))
        return


async def __registerStudent(interaction: discord.Interaction, student: discord.Member, student_name: str):
    teacher = interaction.user
    if not isinstance(teacher, discord.Member):
        raise ValueError("teacher is no member")

    guild = unwrapped(interaction.guild)
    category = unwrapped(discord.utils.get(guild.categories, name=teacher.display_name))

    # No exceptions from here on

    # Update server presence
    await student.edit(nick=student_name)

    # Create a new channel for the student
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        student: discord.PermissionOverwrite(read_messages=True),
        teacher: discord.PermissionOverwrite(read_messages=True)
    }

    channel = await guild.create_text_channel(student_name, category=category, overwrites=overwrites)
    await channel.send(f"👋 Willkommen, {student.mention}! Hier kannst du mit deinem Lehrer {teacher.mention} kommunizieren")


async def __registerTeacher(interaction: discord.Interaction, teacher: discord.Member, teacher_name: str):
    guild = unwrapped(interaction.guild)

    # No exceptions from here on

    # Update server presence
    new_display_name = "🎓 " + teacher_name
    await teacher.edit(nick=new_display_name)

    # Create a new category for the teacher
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        teacher: discord.PermissionOverwrite(read_messages=True)
    }

    category = await guild.create_category(new_display_name, overwrites=overwrites)

    # Create new cmd channel for the teacher
    channel = await guild.create_text_channel("cmd", category=category, overwrites=overwrites)
    await channel.send(f"👋 Willkommen, {teacher.mention}! Hier kannst du Befehle ausführen.")


# @client.tree.command()
# async def deregister(interaction: discord.Interaction, member: discord.Member):
#     """Deregisters a member"""
#     if not isinstance(interaction.user, discord.Member):
#         await interaction.response.send_message("⚠️ Interaktion ist ungültig.")
#         return

#     if not any(role.name in ['Admin', 'Lehrer'] for role in interaction.user.roles):
#         await interaction.response.send_message("⛔ Du bist zur Nutzung dieses Befehls nicht berechtigt.")
#         return

#     if not any(role.name in ['Lehrer', 'Schüler'] for role in member.roles):
#         await interaction.response.send_message(f"⚠️ {member.mention} ist nicht registriert.")
#         return

#     try:
#         if any(role.name == 'Lehrer' for role in member.roles):
#             await __deregisterTeacher(interaction, member)
#         elif any(role.name == 'Schüler' for role in member.roles):
#             await __deregisterStudent(interaction, member)

#         await interaction.response.send_message(f"✅ {member.name} wurde erfolgreich abgemeldet.")

#     except ValueError as e:
#         await interaction.response.send_message("⚠️ Fehler beim Abmelden: " + str(e))
#         return


# async def __deregisterStudent(interaction: discord.Interaction, student: discord.Member):
#     teacher = interaction.user
#     if not isinstance(teacher, discord.Member):
#         raise ValueError("teacher is no member")

#     guild = unwrapped(interaction.guild)
#     category = unwrapped(discord.utils.get(guild.categories, name=teacher.nick))

#     # No exceptions from here on ||| not really

#     # Remove the student role
#     student_role = unwrapped(discord.utils.get(guild.roles, name="Schüler"))
#     await student.remove_roles(student_role)

#     # Update server presence
#     await student.edit(nick=None)

#     # Delete the channel of the student
#     channel = unwrapped(discord.utils.get(category.text_channels, name=student.nick))
#     await channel.delete()
#     pass


# async def __deregisterTeacher(interaction: discord.Interaction, teacher: discord.Member):
#     guild = unwrapped(interaction.guild)

#     # No exceptions from here on ||| not really

#     # Remove the teacher role
#     teacher_role = unwrapped(discord.utils.get(guild.roles, name="Lehrer"))
#     await teacher.remove_roles(teacher_role)

#     # Update server presence
#     await teacher.edit(nick=None)

#     # Delete the category of the teacher
#     category = unwrapped(discord.utils.get(guild.categories, name=teacher.nick))
#     for channel in category.channels:
#         await channel.delete()
#     await category.delete()


def unwrapped[T](value: T | None) -> T:
    """Unwraps a value from an optional type"""
    if value is None:
        raise ValueError(f"Value of {type(value)} is None")
    return value


client.run(TOKEN)
