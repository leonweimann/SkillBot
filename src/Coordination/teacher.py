import discord

import Utils.environment as env

from Utils.database import *
from Utils.errors import *
from Utils.logging import log

import asyncio


# region Assignments

async def assign_teacher(interaction: discord.Interaction, teacher: discord.Member, real_name: str, subjects: str | None = None, phonenumber: str | None = None, availability: str | None = None):
    if interaction.guild is None:
        raise CodeError("Dieser Befehl kann nur in einem Server verwendet werden")

    if env.is_teacher(teacher):
        raise UsageError(f"{teacher.mention} ist bereits ein Lehrer")

    # Begin teacher assignment

    # Setup teacher in db
    db_teacher = Teacher(interaction.guild.id, teacher.id)
    db_teacher.edit(real_name=real_name, subjects=subjects, phonenumber=phonenumber, availability=availability)

    # Configure teachers category
    teacher_category_name = env.generate_member_nick(db_teacher)
    teacher_category = discord.utils.get(interaction.guild.categories, name=teacher_category_name)  # Search for existing category, because maybe there exists one already
    if not teacher_category:
        # Create new teacher category
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            teacher: discord.PermissionOverwrite(read_messages=True)
        }

        teacher_category = await interaction.guild.create_category(teacher_category_name, overwrites=overwrites)

    # Connect teacher category with teacher
    db_teacher.edit(teaching_category=teacher_category.id)

    # Create cmd channel for the teacher
    cmd_channel = await interaction.guild.create_text_channel('cmd', category=teacher_category, overwrites=overwrites)

    # Apply teacher role and nickname
    await teacher.add_roles(env.get_teacher_role(interaction.guild))
    await teacher.edit(nick=env.generate_member_nick(db_teacher))

    await cmd_channel.send(f'👋 Willkommen, {teacher.mention}! Hier kannst du ungestört Befehle ausführen.')


async def unassign_teacher(interaction: discord.Interaction, teacher: discord.Member):
    if not interaction.guild:
        raise CodeError("Dieser Befehl kann nur in einem Server verwendet werden")

    if not env.is_teacher(teacher):
        raise UsageError(f"{teacher.mention} ist kein Lehrer")

    # Begin teacher unassignment

    db_teacher = Teacher(interaction.guild.id, teacher.id)

    # Ensure that teacher has no current students
    teacher_category_name = env.generate_member_nick(db_teacher)
    teacher_category = discord.utils.get(interaction.guild.categories, name=teacher_category_name)

    if teacher_category:
        if [channel.name for channel in teacher_category.text_channels if channel.name != 'cmd'] != []:
            raise UsageError(f"{teacher.mention} hat noch registrierte Schüler")
    else:
        await log(interaction.guild, f"Lehrer {teacher.mention} hat keine Kategorie", details={'Teacher': f'{teacher.mention}'})

    # Reset teacher in db
    db_teacher.pop()

    # Remove teacher role and nickname
    await teacher.remove_roles(env.get_teacher_role(interaction.guild))
    await teacher.edit(nick=None)

    # Delete channels and category
    if teacher_category:
        for channel in teacher_category.text_channels:
            await channel.delete()
        await teacher_category.delete()

# endregion


# region Sort Channels


# TODO: Fix sorting - doesn't work properly
async def sort_channels(channel: discord.abc.GuildChannel):
    """
    Sortiert Channels in einer Kategorie, die '🎓' im Namen trägt.
    Der 'cmd'-Channel bleibt immer an erster Stelle.
    """
    # Prüfe, ob der Channel zu einer relevanten Kategorie gehört
    if channel.category and ('🎓' in channel.category.name or env.get_archive_channel(channel.guild)):
        channels = channel.category.channels
        cmd_channel = next((c for c in channels if c.name == 'cmd'), None)
        other_channels = sorted((c for c in channels if c.name != 'cmd'), key=lambda c: c.name.lower())

        tasks = []
        position = 0

        # Setze 'cmd' immer an die erste Stelle, falls vorhanden
        if cmd_channel:
            if cmd_channel.position != 0:
                tasks.append(cmd_channel.edit(position=0))
            position = 1

        # Setze die restlichen Channels in sortierter Reihenfolge
        for c in other_channels:
            if c.position != position:
                tasks.append(c.edit(position=position))
            position += 1

        # Starte alle Änderungen parallel
        if tasks:
            await asyncio.gather(*tasks)

# endregion
