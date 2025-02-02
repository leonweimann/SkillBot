import discord

from Utils.channels import get_category_by_name, get_channel_by_name
from Utils.database import *
import Utils.environment as env
from Utils.errors import CodeError, UsageError
from Utils.members import get_student_nick, get_member_by_user, generate_student_channel_name
from Utils.roles import get_student_role, get_teacher_role


async def assign_student(interaction: discord.Interaction, student: discord.Member, name: str, silent: bool = False):
    if interaction.guild is None:
        raise CodeError("Guild is None")

    teacher = get_member_by_user(interaction.guild, interaction.user)

    if get_teacher_role(interaction.guild) not in teacher.roles:
        raise UsageError(f"{teacher.mention} ist kein Lehrer")

    student_role = get_student_role(interaction.guild)

    if student_role in student.roles:
        raise UsageError(f"{student.mention} ist bereits ein registrierter Schüler")

    teachers_category = get_category_by_name(interaction.guild, teacher.display_name)

    overwrites = {
        interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
        student: discord.PermissionOverwrite(read_messages=True),
        teacher: discord.PermissionOverwrite(read_messages=True)
    }

    new_student_channel = await interaction.guild.create_text_channel(name, category=teachers_category, overwrites=overwrites)

    # Only add roles and nick if channel was created successfully
    await student.add_roles(student_role)
    await student.edit(nick=get_student_nick(name))

    assign_student_database(interaction.user.id, student.id, name)

    if not silent:
        await new_student_channel.send(f"👋 Willkommen, {student.mention}! Hier kannst du mit deinem Lehrer {teacher.mention} kommunizieren")


def assign_student_database(teacher_id: int, student_id: int, real_name: str):
    db_user = DBUser(student_id)
    db_user.edit(real_name=real_name, icon='🎒', user_type='student')
    DatabaseManager.add_student_teacher(student_id, teacher_id)


async def unassign_student(interaction: discord.Interaction, student: discord.Member):
    if interaction.guild is None:
        raise CodeError('Guild is None')

    teacher = get_member_by_user(interaction.guild, interaction.user)

    if get_teacher_role(interaction.guild) not in teacher.roles:
        raise UsageError(f"{teacher.mention} ist kein Lehrer")

    student_role = get_student_role(interaction.guild)

    if student_role not in student.roles:
        raise UsageError(f"{student.mention} ist kein registrierter Schüler")

    student_name = DBUser(student.id).real_name
    if student_name is None:
        raise CodeError(f"Student {student.id} has no real name")

    student_channel = get_channel_by_name(interaction.guild, generate_student_channel_name(student_name))
    await student_channel.delete()

    unassign_student_database(student.id)

    await student.remove_roles(student_role)
    await student.edit(nick=None)


def unassign_student_database(student_id: int):
    db_user = DBUser(student_id)
    db_user.edit(icon=None, user_type=None)
    DatabaseManager.remove_student_teacher(student_id)


async def stash_student(interaction: discord.Interaction, student: discord.Member):
    if interaction.guild is None:
        raise CodeError('Guild is None')

    if env.get_student_role(interaction.guild) not in student.roles:
        raise UsageError(f"{student.mention} ist kein registrierter Schüler")

    teacher_id = DBUser(student.id).teacher_id
    if teacher_id is None:
        raise CodeError(f"Student {student.id} has no teacher")
    elif teacher_id != interaction.user.id:
        raise UsageError(f"{student.mention} ist nicht dein Schüler")

    student_name = DBUser(student.id).real_name
    if student_name is None:
        raise CodeError(f"Student {student.id} has no real name")

    student_channel = get_channel_by_name(interaction.guild, generate_student_channel_name(student_name))
    archive_channel = env.get_archive_channel(interaction.guild)
    if student_channel.category == archive_channel:
        raise UsageError(f"{student.mention} ist bereits archiviert")

    await student_channel.edit(category=archive_channel)


async def pop_student(interaction: discord.Interaction, student: discord.Member):
    if interaction.guild is None:
        raise CodeError('Guild is None')

    if env.get_student_role(interaction.guild) not in student.roles:
        raise UsageError(f"{student.mention} ist kein registrierter Schüler")

    teacher_id = DBUser(student.id).teacher_id
    if teacher_id is None:
        raise CodeError(f"Student {student.id} has no teacher")
    elif teacher_id != interaction.user.id:
        raise UsageError(f"{student.mention} ist nicht dein Schüler")

    student_name = DBUser(student.id).real_name
    if student_name is None:
        raise CodeError(f"Student {student.id} has no real name")

    student_channel = get_channel_by_name(interaction.guild, generate_student_channel_name(student_name))
    archive_channel = env.get_archive_channel(interaction.guild)
    if student_channel.category != archive_channel:
        raise UsageError(f"{student.mention} ist nicht archiviert")

    await student_channel.edit(category=get_category_by_name(interaction.guild, interaction.user.display_name))
