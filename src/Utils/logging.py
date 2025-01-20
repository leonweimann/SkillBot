from discord import Guild

from .channels import get_channel_by_name
from .errors import CodeError


async def log(guild: Guild, message: str):
    logs_channel = get_channel_by_name(guild, "logs")
    if logs_channel is None:
        raise CodeError("Logs channel not found")
    await logs_channel.send(message)
