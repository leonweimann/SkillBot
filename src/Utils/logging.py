import discord

import Utils.environment as env


async def log(guild: discord.Guild, message: str, details: dict[str, str] = {}):
    """
    Logs a message to the logs channel of the given guild.

    Args:
        guild (discord.Guild): The guild in which to log the message.
        message (str): The message to log.
        details (dict[str, str], optional): Additional details to log. Defaults to {}.
    """
    logs_channel = env.get_log_channel(guild)

    msg = f'{"-" * 20}\n**[LOG]** {message}\n```'
    if details:
        max_key_length = max(len(key) for key in details.keys())
        for key, value in details.items():
            msg += f'{key}{" " * (max_key_length - len(key))} | {value if value != '' else 'None'}\n'
    msg += '```'
    msg += f'\n{"-" * 20}'
    await logs_channel.send(msg)
