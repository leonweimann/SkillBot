from typing import Iterable

import discord

from Utils.database import DBUser
from Utils.errors import CodeError


def get_archive_channel(guild: discord.Guild) -> discord.CategoryChannel:
    return __unwrapped_get(guild.categories, '📚 Wissensbereich')


def get_student_role(guild: discord.Guild) -> discord.Role:
    return __unwrapped_get(guild.roles, 'Schüler')


def get_teacher_role(guild: discord.Guild) -> discord.Role:
    return __unwrapped_get(guild.roles, 'Lehrer')


def get_admin_role(guild: discord.Guild) -> discord.Role:
    return __unwrapped_get(guild.roles, 'Admin')


def __unwrapped_get[T](iterable: Iterable[T], name: str) -> T:
    result = discord.utils.get(iterable, name=name)
    if result is None:
        raise CodeError(f'{name} not found')
    return result


def get_member(guild: discord.Guild, id: int) -> discord.Member:
    result = discord.utils.get(guild.members, id=id)
    if result is None:
        raise CodeError(f'Member with ID {id} not found')
    return result


def is_student(member: discord.Member) -> bool:
    return get_student_role(member.guild) in member.roles


def is_teacher(member: discord.Member) -> bool:
    return get_teacher_role(member.guild) in member.roles


def is_admin(member: discord.Member) -> bool:
    return get_admin_role(member.guild) in member.roles


def generate_member_nick(db_member: DBUser) -> str:
    return f'{db_member.icon} {db_member.real_name}'


def generate_student_channel_name(student_name: str):
    return student_name.lower().replace(' ', '-')
