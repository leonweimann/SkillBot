from typing import Iterable

import discord

from Utils.errors import CodeError


def get_archive_channel(guild: discord.Guild) -> discord.CategoryChannel:
    return __unwrapped_get(guild.categories, '📚 Wissensbereich')


def get_student_role(guild: discord.Guild) -> discord.Role:
    return __unwrapped_get(guild.roles, 'Schüler')


def get_teacher_role(guild: discord.Guild) -> discord.Role:
    return __unwrapped_get(guild.roles, 'Lehrer')


def get_member(guild: discord.Guild, id: int) -> discord.Member:
    result = discord.utils.get(guild.members, id=id)
    if result is None:
        raise CodeError(f'Member with ID {id} not found')
    return result


def __unwrapped_get[T](iterable: Iterable[T], name: str) -> T:
    result = discord.utils.get(iterable, name=name)
    if result is None:
        raise CodeError(f'{name} not found')
    return result
