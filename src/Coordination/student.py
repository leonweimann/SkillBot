import discord

from Utils.database import *
import Utils.environment as env
from Utils.errors import *
from Utils.logging import log


# region Assignments

async def assign_student(interaction: discord.Interaction, student: discord.Member, name: str, silent: bool = False):
    if not interaction.guild:
        raise CodeError("Dieser Befehl kann nur in einem Server verwendet werden")

    if not isinstance(teacher := interaction.user, discord.Member):
        raise CodeError("Dieser Befehl kann nur von Mitgliedern verwendet werden")

    if not env.is_teacher(teacher):
        raise UsageError(f"Du {teacher.mention} bist kein Lehrer")

    if env.is_student(student):
        raise UsageError(f"{student.mention} ist bereits ein registrierter Schüler")

    # Begin student assignment

    student_channel_name = env.generate_student_channel_name(name)
    student_channel = env.__unwrapped_get(interaction.guild.text_channels, student_channel_name)  # Search for student channel, because maybe there exists one already
    if not student_channel:
        # Create student channel
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            student: discord.PermissionOverwrite(read_messages=True),
            teacher: discord.PermissionOverwrite(read_messages=True)
        }

        teachers_category = env.__unwrapped_get(interaction.guild.categories, teacher.display_name)
        student_channel = await interaction.guild.create_text_channel(student_channel_name, category=teachers_category, overwrites=overwrites)

    # Setup student in db
    db_student = DBUser(student.id)
    db_student.edit(real_name=name, icon='🎒', user_type='student')

    # Create teacher-student connection in db
    ts_con = TeacherStudentConnection(student.id)
    ts_con.edit(teacher_id=teacher.id, channel_id=student_channel.id)

    # Apply student role and nickname
    await student.add_roles(env.get_student_role(interaction.guild))
    await student.edit(nick=env.generate_member_nick(db_student))

    # Send a welcome message if not silent
    if not silent:
        await student_channel.send(f"👋 Willkommen, {student.mention}! Hier kannst du mit deinem Lehrer {teacher.mention} kommunizieren")


async def unassign_student(interaction: discord.Interaction, student: discord.Member):
    if not interaction.guild:
        raise CodeError("Dieser Befehl kann nur in einem Server verwendet werden")

    if not isinstance(teacher := interaction.user, discord.Member):
        raise CodeError("Dieser Befehl kann nur von Mitgliedern verwendet werden")

    if not env.is_teacher(teacher):
        raise UsageError(f"Du {teacher.mention} bist kein Lehrer")

    if not env.is_student(student):
        raise UsageError(f"{student.mention} ist kein registrierter Schüler")

    # Begin student unassignment

    student_name = DBUser(student.id).real_name
    if not student_name:
        raise CodeError(f"Schüler {student.id} hat keinen echten Namen")

    ts_con = TeacherStudentConnection(student.id)
    if not ts_con.channel_id:  # TODO: log if not found?
        raise CodeError(f"Schüler {student.id} hat keine Lehrer-Schüler-Verbindung")

    if ts_con.teacher_id != teacher.id:
        raise UsageError(f"{student.mention} ist nicht dein Schüler")

    student_channel = interaction.guild.get_channel(ts_con.channel_id)
    if student_channel:
        await student_channel.delete()
    else:
        # Log if no channel was found, but still continue unassignment
        await log(interaction.guild, f"Channel für {student.mention} nicht gefunden, sollte aber `{ts_con.channel_id}` sein")

    # Reset user to default member in db
    db_student = DBUser(student.id)
    db_student.edit(icon=None, user_type=None)

    # Remove teacher-student connection in db
    TeacherStudentConnection(student.id).remove()

    # Remove student role and nickname
    await student.remove_roles(env.get_student_role(interaction.guild))
    await student.edit(nick=None)

# endregion


# region Stashing

async def stash_student(interaction: discord.Interaction, student: discord.Member):
    if interaction.guild is None:
        raise CodeError('Guild is None')

    if env.get_student_role(interaction.guild) not in student.roles:
        raise UsageError(f"{student.mention} ist kein registrierter Schüler")

    teacher_id = TeacherStudentConnection(student.id).teacher_id
    if teacher_id is None:
        raise CodeError(f"Student {student.id} has no teacher")
    elif teacher_id != interaction.user.id:
        raise UsageError(f"{student.mention} ist nicht dein Schüler")

    student_channel_id = TeacherStudentConnection(student.id).channel_id
    student_channel = discord.utils.get(interaction.guild.text_channels, id=student_channel_id)
    if student_channel is None:
        raise CodeError(f"Student {student.id} has no channel")

    archive_channel = env.get_archive_channel(interaction.guild)
    if student_channel.category == archive_channel:
        raise UsageError(f"{student.mention} ist bereits archiviert")

    await student_channel.edit(category=archive_channel)


async def pop_student(interaction: discord.Interaction, student: discord.Member):
    if interaction.guild is None:
        raise CodeError('Guild is None')

    if env.get_student_role(interaction.guild) not in student.roles:
        raise UsageError(f"{student.mention} ist kein registrierter Schüler")

    teacher_id = TeacherStudentConnection(student.id).teacher_id
    if teacher_id is None:
        raise CodeError(f"Student {student.id} has no teacher")
    elif teacher_id != interaction.user.id:
        raise UsageError(f"{student.mention} ist nicht dein Schüler")

    student_channel_id = TeacherStudentConnection(student.id).channel_id
    student_channel = discord.utils.get(interaction.guild.text_channels, id=student_channel_id)
    if student_channel is None:
        raise CodeError(f"Student {student.id} has no channel")

    archive_channel = env.get_archive_channel(interaction.guild)
    if student_channel.category != archive_channel:
        raise UsageError(f"{student.mention} ist nicht archiviert")

    await student_channel.edit(category=env.__unwrapped_get(interaction.guild.categories, interaction.user.display_name))

# endregion


# region Connecting


# endregion
