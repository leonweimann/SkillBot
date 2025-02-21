import discord

from Utils.database import DBUser
import Utils.environment as env
from Utils.errors import *


# region Assignments

async def assign_teacher(interaction: discord.Interaction, teacher: discord.Member, name: str):
    if interaction.guild is None:
        raise CodeError("Dieser Befehl kann nur in einem Server verwendet werden")

    if env.is_teacher(teacher):
        raise UsageError(f"{teacher.mention} ist bereits ein Lehrer")

    # Begin teacher assignment

    # Setup teacher in db
    db_teacher = DBUser(teacher.id)
    db_teacher.edit(real_name=name, icon='🎓', user_type='teacher')

    # Configure teachers category
    teacher_category_name = env.generate_member_nick(db_teacher)
    teacher_category = env.__unwrapped_get(interaction.guild.categories, teacher_category_name)  # Search for teacher category, because maybe there exists one already
    if not teacher_category:
        # Create new teacher category
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            teacher: discord.PermissionOverwrite(read_messages=True)
        }

        teacher_category = await interaction.guild.create_category(teacher_category_name, overwrites=overwrites)

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

    db_teacher = DBUser(teacher.id)

    # Ensure that teacher has no current students
    teacher_category_name = env.generate_member_nick(db_teacher)
    teacher_category = env.__unwrapped_get(interaction.guild.categories, teacher_category_name)
    if [channel.name for channel in teacher_category.text_channels if channel.name != 'cmd'] != []:
        raise UsageError(f"{teacher.mention} hat noch registrierte Schüler")

    # Reset teacher in db
    db_teacher.edit(icon=None, user_type=None)

    # Remove teacher role and nickname
    await teacher.remove_roles(env.get_teacher_role(interaction.guild))
    await teacher.edit(nick=None)

    # Delete channels and category
    for channel in teacher_category.text_channels:
        await channel.delete()
    await teacher_category.delete()

# endregion
