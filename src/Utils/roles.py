import discord


def get_teacher_role(guild: discord.Guild) -> discord.Role:
    return __get_role_by_name(guild, 'Lehrer')


def get_student_role(guild: discord.Guild) -> discord.Role:
    return __get_role_by_name(guild, 'Schüler')


def __get_role_by_name(guild: discord.Guild, role_name: str) -> discord.Role:
    role = discord.utils.get(guild.roles, name=role_name)
    if role is None:
        raise ValueError(f"Role '{role_name}' not found")
    return role
