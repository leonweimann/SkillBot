import discord

import Utils.environment as env

from Utils.database import *
from Utils.errors import *
from Utils.logging import log


# region Assignments

async def assign_student(interaction: discord.Interaction, student: discord.Member, real_name: str, customer_id: int, major: str | None = None, silent: bool = False):
    """
    Assign a student to a teacher in a Discord server.

    This function assigns a student to a teacher by creating a dedicated text channel for communication,
    setting up the student in the database, and applying the necessary roles and nicknames.

    Args:
        interaction (discord.Interaction): The interaction that triggered the command.
        student (discord.Member): The student to be assigned.
        name (str): The real name of the student.
        silent (bool, optional): If True, no welcome message will be sent. Defaults to False.

    Raises:
        CodeError: If the command is used outside of a server or by a non-member.
        UsageError: If the user is not a teacher or the student is already registered.

    """
    if not interaction.guild:
        raise CodeError("Dieser Befehl kann nur in einem Server verwendet werden")

    if not isinstance(teacher := interaction.user, discord.Member):
        raise CodeError("Dieser Befehl kann nur von Mitgliedern verwendet werden")

    if not env.is_teacher(teacher):
        raise UsageError(f"Du {teacher.mention} bist kein Lehrer")

    if env.is_student(student):
        raise UsageError(f"{student.mention} ist bereits ein registrierter Schüler")

    # Begin student assignment

    student_channel_name = env.generate_student_channel_name(real_name)
    student_channel = discord.utils.get(interaction.guild.text_channels, name=student_channel_name)  # Search for student channel, because maybe there exists one already
    if not student_channel:
        # Create student channel
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            student: discord.PermissionOverwrite(read_messages=True),
            teacher: discord.PermissionOverwrite(read_messages=True)
        }

        db_teacher = Teacher(interaction.user.id)

        teachers_category = discord.utils.get(interaction.guild.categories, id=db_teacher.teaching_category)
        if teachers_category:
            student_channel = await interaction.guild.create_text_channel(student_channel_name, category=teachers_category, overwrites=overwrites)
        else:
            raise CodeError(f"Lehrer {teacher.mention} hat keine Kategorie")

    # Setup student in db
    db_student = Student(student.id)
    db_student.edit(real_name=real_name, major=major, customer_id=customer_id)

    # Create teacher-student connection in db
    db_student.connect_teacher(teacher.id, student_channel.id)

    # Apply student role and nickname
    await student.add_roles(env.get_student_role(interaction.guild))
    await student.edit(nick=env.generate_member_nick(db_student))

    # Send a welcome message if not silent
    if not silent:
        await student_channel.send(f"👋 Willkommen, {student.mention}! Hier kannst du mit deinem Lehrer {teacher.mention} kommunizieren")


async def unassign_student(interaction: discord.Interaction, student: discord.Member):
    """
    Unassign a student from a teacher in a Discord server.

    This function performs the following steps:
    1. Validates that the command is used within a server and by a member.
    2. Checks if the user issuing the command is a teacher.
    3. Checks if the specified student is registered.
    4. Verifies the teacher-student connection.
    5. Deletes the student-teacher channel if it exists.
    6. Resets the student's database entry to default.
    7. Removes the teacher-student connection from the database.
    8. Removes the student role and nickname from the student.

    Args:
        interaction (discord.Interaction): The interaction object representing the command invocation.
        student (discord.Member): The Discord member object representing the student to be unassigned.

    Raises:
        CodeError: If the command is not used in a server, or if the student has no real name, or if no teacher-student connection is found.
        UsageError: If the user issuing the command is not a teacher, or if the specified student is not registered, or if the student is not assigned to the teacher.
    """
    if not interaction.guild:
        raise CodeError("Dieser Befehl kann nur in einem Server verwendet werden")

    if not isinstance(teacher := interaction.user, discord.Member):
        raise CodeError("Dieser Befehl kann nur von Mitgliedern verwendet werden")

    if not env.is_teacher(teacher):
        raise UsageError(f"Du {teacher.mention} bist kein Lehrer")

    if not env.is_student(student):
        raise UsageError(f"{student.mention} ist kein registrierter Schüler")

    # Begin student unassignment

    db_student = Student(student.id)
    if not db_student.real_name:
        raise CodeError(f"Schüler {student.id} hat keinen echten Namen")

    ts_con = TeacherStudentConnection.find_by_student(student.id)
    if not ts_con:
        raise CodeError(f"Schüler {student.id} hat keine Lehrer-Schüler-Verbindung")

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

    # Reset user to default member in db and remove teacher-student connection
    db_student.pop()

    # Remove student role and nickname
    await student.remove_roles(env.get_student_role(interaction.guild))
    await student.edit(nick=None)

# endregion


# region Stashing

async def stash_student(interaction: discord.Interaction, student: discord.Member):
    """
    Archives a student's channel by moving it to the archive category.

    Args:
        interaction (discord.Interaction): The interaction that triggered the command.
        student (discord.Member): The student to be archived.

    Raises:
        CodeError: If the guild is None, the student has no teacher, or the student's channel is not found.
        UsageError: If the student is not registered, the student is not assigned to the user, or the student is already archived.
    """
    if interaction.guild is None:
        raise CodeError('Guild is None')

    if env.get_student_role(interaction.guild) not in student.roles:
        raise UsageError(f"{student.mention} ist kein registrierter Schüler")

    ts_con = TeacherStudentConnection.find_by_student(student.id)
    if not ts_con:
        raise CodeError(f"Schüler {student.id} hat keine Lehrer-Schüler-Verbindung")

    if ts_con.teacher_id is None:
        raise CodeError(f"Student {student.id} has no teacher")
    elif ts_con.teacher_id != interaction.user.id:
        raise UsageError(f"{student.mention} ist nicht dein Schüler")

    student_channel = discord.utils.get(interaction.guild.text_channels, id=ts_con.channel_id)
    if student_channel is None:
        raise CodeError(f"Student {student.id} has no channel")

    archive_channel = env.get_archive_channel(interaction.guild)
    if student_channel.category == archive_channel:
        raise UsageError(f"{student.mention} ist bereits archiviert")

    await student_channel.edit(category=archive_channel)


async def pop_student(interaction: discord.Interaction, student: discord.Member):
    """
    Asynchronously handles the removal of a student from a teacher's list.

    This function performs several checks to ensure the student is valid and belongs to the teacher
    invoking the command. It also verifies that the student's channel is archived before moving it
    to the teacher's category.

    Args:
        interaction (discord.Interaction): The interaction object representing the command invocation.
        student (discord.Member): The Discord member object representing the student to be removed.

    Raises:
        CodeError: If the guild is None, the student has no teacher, or the student's channel is not found.
        UsageError: If the student is not registered, does not belong to the invoking teacher, or is not archived.
    """
    if interaction.guild is None:
        raise CodeError('Guild is None')

    if env.get_student_role(interaction.guild) not in student.roles:
        raise UsageError(f"{student.mention} ist kein registrierter Schüler")

    ts_con = TeacherStudentConnection.find_by_student(student.id)
    if not ts_con:
        raise CodeError(f"Schüler {student.id} hat keine Lehrer-Schüler-Verbindung")

    if ts_con.teacher_id is None:
        raise CodeError(f"Student {student.id} has no teacher")
    elif ts_con.teacher_id != interaction.user.id:
        raise UsageError(f"{student.mention} ist nicht dein Schüler")

    student_channel = discord.utils.get(interaction.guild.text_channels, id=ts_con.channel_id)
    if student_channel is None:
        raise CodeError(f"Student {student.id} has no channel")

    archive_channel = env.get_archive_channel(interaction.guild)
    if student_channel.category != archive_channel:
        raise UsageError(f"{student.mention} ist nicht archiviert")

    db_teacher = Teacher(ts_con.teacher_id)
    if not db_teacher.teaching_category:
        raise CodeError(f"Lehrer {interaction.user.mention} hat keine Kategorie")

    teacher_category = discord.utils.get(interaction.guild.categories, id=db_teacher.teaching_category)
    if not teacher_category:
        raise CodeError(f"Lehrer {interaction.user.mention} hat keine Kategorie")

    await student_channel.edit(category=teacher_category)

# endregion


# region Connecting

async def connect_student(interaction: discord.Interaction, student: discord.Member, other_account: discord.Member):
    """
    Asynchronously connects a student with another account in a Discord server.

    This function sets the necessary permissions for the other account to access the student's channel
    and updates the nickname and roles of the other account to reflect the connection.

    Args:
        interaction (discord.Interaction): The interaction that triggered the command.
        student (discord.Member): The student to be connected.
        other_account (discord.Member): The account to be connected with the student.

    Raises:
        CodeError: If the command is not used in a server, if the student does not have a teacher-student connection,
                   or if the channel for the student is not found.
        UsageError: If the other account is already a registered student or if the user is not the teacher of the student.
    """
    if not interaction.guild:
        raise CodeError("Dieser Befehl kann nur in einem Server verwendet werden")

    if env.is_student(other_account):
        raise UsageError(f"{other_account.mention} ist ein registrierter Schüler und kann nicht mit {student.mention} verbunden werden")

    ts_con = TeacherStudentConnection.find_by_student(student.id)
    if not ts_con:
        raise CodeError(f"Schüler {student.id} hat keine Lehrer-Schüler-Verbindung gefunden")

    if ts_con.teacher_id != interaction.user.id:
        raise UsageError("Du kannst nur deine eigenen Schüler verbinden")

    student_channel = interaction.guild.get_channel(ts_con.channel_id)
    if not student_channel:
        raise CodeError(f"Channel für Schüler {student.id} nicht gefunden")

    await student_channel.set_permissions(other_account, read_messages=True, send_messages=True)
    await other_account.edit(nick=f'{student.nick} ({other_account.display_name})')
    await other_account.add_roles(env.get_student_role(interaction.guild))


async def disconnect_student(interaction: discord.Interaction, student: discord.Member, other_account: discord.Member):
    """
    Asynchronously disconnects a student from a teacher-student connection in a Discord server.

    Args:
        interaction (discord.Interaction): The interaction that triggered the command.
        student (discord.Member): The student to be disconnected.
        other_account (discord.Member): The other account to remove permissions from.

    Raises:
        CodeError: If the command is used outside of a server, if the student has no teacher-student connection,
                   if the channel for the student is not found, or if the user is not the teacher of the student.
        UsageError: If the user is not the teacher of the student.

    Notes:
        This function removes the permissions of the other account from the student's channel,
        resets the nickname of the other account, and removes the student role from the other account.
    """
    if not interaction.guild:
        raise CodeError("Dieser Befehl kann nur in einem Server verwendet werden")

    ts_con = TeacherStudentConnection.find_by_student(student.id)
    if not ts_con:
        raise CodeError(f"Schüler {student.id} hat keine Lehrer-Schüler-Verbindung gefunden")

    if ts_con.teacher_id != interaction.user.id:
        raise UsageError("Du kannst nur deine eigenen Schüler trennen")

    student_channel = interaction.guild.get_channel(ts_con.channel_id)
    if not student_channel:
        raise CodeError(f"Channel für Schüler {student.id} nicht gefunden")

    await student_channel.set_permissions(other_account, overwrite=None)
    await other_account.edit(nick=None)
    await other_account.remove_roles(env.get_student_role(interaction.guild))

# endregion
