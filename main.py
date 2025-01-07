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


def ensure_user_permission(interaction: discord.Interaction, required_role_name: str) -> bool:
    return False


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
    required_roles: dict[str, list[str]] = {'Lehrer': ['Admin'], 'Schüler': ['Admin', 'Lehrer']}

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

    await member.add_roles(role)

    if role.name == 'Lehrer':
        await __registerTeacher(interaction, member, member_name)
    elif role.name == 'Schüler':
        await __registerStudent(interaction, member, member_name)

    await interaction.response.send_message(f"✅ {member.name} wurde erfolgreich registriert.")


async def __registerStudent(interaction: discord.Interaction, student: discord.Member, student_name: str):
    pass


async def __registerTeacher(interaction: discord.Interaction, teacher: discord.Member, teacher_name: str):
    pass


client.run(TOKEN)
