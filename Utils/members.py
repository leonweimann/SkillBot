import discord

from Utils.errors import CodeError


def get_student_nick(name: str) -> str:
    return f'🎒 {name}'


def get_teacher_nick(name: str) -> str:
    return f'🎓 {name}'


def get_name_by_nick(nick: str) -> str:
    return nick[2:]


def get_member_by_user(guild: discord.Guild, user: discord.User | discord.Member) -> discord.Member:
    if isinstance(user, discord.Member):
        return user

    member = guild.get_member(user.id)
    if member is None:
        raise CodeError("User is not a member")
    return member