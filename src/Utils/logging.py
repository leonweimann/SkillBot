from discord import Guild

from .channels import get_channel_by_name
from .errors import CodeError


async def log(guild: Guild, message: str, details: dict[str, str] = {}):
    logs_channel = get_channel_by_name(guild, "logs")
    if logs_channel is None:
        raise CodeError("Logs channel not found")

    res = f'{"-" * 20}\n**[LOG]** {message}\n```'
    if details:
        max_key_length = max(len(key) for key in details.keys())
        for key, value in details.items():
            res += f'{key}{" " * (max_key_length - len(key))} | {value}\n'
    res += '```'
    res += f'\n{"-" * 20}'
    await logs_channel.send(res)
