import discord

from Utils.channels import get_category_by_name, get_channel_by_name
from Utils.errors import CodeError, UsageError
from Utils.members import get_student_nick, get_name_by_nick, get_member_by_user
from Utils.roles import get_student_role, get_teacher_role


async def assign_student(interaction: discord.Interaction, student: discord.Member, name: str):
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

    await new_student_channel.send(f"👋 Willkommen, {student.mention}! Hier kannst du mit deinem Lehrer {teacher.mention} kommunizieren")


async def unassign_student(interaction: discord.Interaction, student: discord.Member):
    if interaction.guild is None:
        raise CodeError('Guild is None')

    teacher = get_member_by_user(interaction.guild, interaction.user)

    if get_teacher_role(interaction.guild) not in teacher.roles:
        raise UsageError(f"{teacher.mention} ist kein Lehrer")

    student_role = get_student_role(interaction.guild)

    if student_role not in student.roles:
        raise UsageError(f"{student.mention} ist kein registrierter Schüler")

    # First remove roles and nick, because channel might never existed?
    # Regardless of that, in any case from here on the nick and role should be removed.
    await student.remove_roles(student_role)
    await student.edit(nick=None)

    # Delete students channel
    student_channel = get_channel_by_name(interaction.guild, get_name_by_nick(student.display_name))
    await student_channel.delete()
