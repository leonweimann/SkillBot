import discord

import Utils.environment as env

from Utils.database import *
from Utils.errors import *
from Utils.lwlogging import log

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


# region Rename

async def rename_teacher(interaction: discord.Interaction, teacher: discord.Member, new_name: str) -> str:
    """
    Renames a teacher in the system by updating their real name in the database, 
    changing their nickname, and updating their associated category name.

    Args:
        interaction (discord.Interaction): The interaction object representing the command invocation.
        teacher (discord.Member): The Discord member object representing the teacher to be renamed.
        new_name (str): The new name to assign to the teacher.

    Returns:
        str: The old name of the teacher before the rename.

    Raises:
        CodeError: If the command is not used in a server, or the teacher does not have a name.
        UsageError: If the user is not an admin or the specified member is not a teacher.
    """
    if not interaction.guild:
        raise CodeError("Dieser Befehl kann nur in einem Server verwendet werden")

    if not isinstance(interaction.user, discord.Member):
        raise CodeError("Dieser Befehl kann nur von einem Mitglied verwendet werden")

    if not env.is_admin(interaction.user):
        raise UsageError("Du bist kein Admin")

    if not env.is_teacher(teacher):
        raise UsageError(f"{teacher.mention} ist kein Lehrer")

    # Get teacher from db
    db_teacher = Teacher(interaction.guild.id, teacher.id)
    if not db_teacher.real_name:
        raise CodeError(f"{teacher.mention} hat keinen Namen")

    old_name = str(db_teacher.real_name)

    # Rename teacher in database
    db_teacher.edit(real_name=new_name)
    # Update teacher nickname
    await teacher.edit(nick=env.generate_member_nick(db_teacher))
    # Update teacher category name
    if teacher_category := discord.utils.get(interaction.guild.categories, id=db_teacher.teaching_category):
        await teacher_category.edit(name=env.generate_member_nick(db_teacher))
    else:
        await log(interaction.guild, f"Lehrer {teacher.mention} hat keine Kategorie", details={'Teacher': f'{teacher.mention}'})

    return old_name


# endregion
