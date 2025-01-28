import discord

from Utils.channels import get_category_by_name
from Utils.database import DBUser
from Utils.errors import CodeError, UsageError
from Utils.members import get_teacher_nick
from Utils.roles import get_teacher_role


async def assign_teacher(interaction: discord.Interaction, teacher: discord.Member, name: str):
    if interaction.guild is None:
        raise CodeError("Guild is None")

    teacher_role = get_teacher_role(interaction.guild)

    if teacher_role in teacher.roles:
        raise UsageError(f"{teacher.mention} ist bereits ein Lehrer")

    teacher_nick = get_teacher_nick(name)

    await teacher.add_roles(teacher_role)
    await teacher.edit(nick=teacher_nick)

    overwrites = {
        interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
        teacher: discord.PermissionOverwrite(read_messages=True)
    }

    new_teacher_category = await interaction.guild.create_category(teacher_nick, overwrites=overwrites)
    new_teacher_cmd_channel = await interaction.guild.create_text_channel('cmd', category=new_teacher_category, overwrites=overwrites)

    assign_teacher_database(teacher.id, name)

    await new_teacher_cmd_channel.send(f"👋 Willkommen, {teacher.mention}! Hier kannst du ungestört Befehle ausführen.")


def assign_teacher_database(teacher_id: int, real_name: str):
    db_user = DBUser(teacher_id)
    db_user.edit(real_name=real_name, icon='🎓', user_type='teacher')


async def unassign_teacher(interaction: discord.Interaction, teacher: discord.Member):
    if interaction.guild is None:
        raise CodeError('Guild is None')

    teacher_role = get_teacher_role(interaction.guild)

    if teacher_role not in teacher.roles:
        raise UsageError(f"{teacher.mention} ist kein Lehrer")

    # Ensure that teacher has no current students
    teacher_category = get_category_by_name(interaction.guild, teacher.display_name)
    for channel in teacher_category.text_channels:
        if channel.name != 'cmd':
            raise UsageError(f"{teacher.mention} hat noch registrierte Schüler")

    await teacher.remove_roles(teacher_role)
    await teacher.edit(nick=None)

    for channel in teacher_category.text_channels:
        await channel.delete()
    await teacher_category.delete()

    unassign_teacher_database(teacher.id)


def unassign_teacher_database(teacher_id: int):
    db_user = DBUser(teacher_id)
    db_user.edit(icon=None, user_type=None)
