import discord

from Utils.errors import CodeError


def get_channel_by_name(guild: discord.Guild, name: str) -> discord.TextChannel:
    channel = discord.utils.get(guild.text_channels, name=name)
    if channel is None:
        raise CodeError(f"Channel {name} not found")
    return channel


def get_category_by_name(guild: discord.Guild, name: str) -> discord.CategoryChannel:
    category = discord.utils.get(guild.categories, name=name)
    if category is None:
        raise CodeError(f"Category {name} not found")
    return category
