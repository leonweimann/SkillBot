from typing import Iterable

import discord

from Utils.database import *
from Utils.errors import *
from Utils.logging import log


# region Helpers

def __unwrapped_get[T](iterable: Iterable[T], name: str) -> T:
    if result := discord.utils.get(iterable, name=name):
        return result
    raise CodeError(f'{name} `({type(iterable)})` not found')


async def send_safe_response(interaction: discord.Interaction, content: str, ephemeral=False):
    """
    Sends a response to the interaction, handling both deferred and immediate responses.

    Args:
        interaction (discord.Interaction): The interaction to respond to.
        content (str): The content of the response.
        ephemeral (bool): Whether the response should be ephemeral (only visible to the user).
    """
    try:
        await interaction.response.send_message(content, ephemeral=ephemeral)
    except discord.errors.HTTPException as e:
        # 40060 bedeutet "Interaction has already been acknowledged"
        if e.code == 40060:
            await interaction.followup.send(content, ephemeral=ephemeral)
        else:
            raise


async def handle_app_command_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError, command_name: str, reqired_role: str = ''):
    """
    Handles errors that occur during the execution of an application command.

    Args:
        interaction (discord.Interaction): The interaction that triggered the command.
        error (discord.app_commands.AppCommandError): The error that occurred.
        command_name (str): The name of the command that was executed.
        reqired_role (str, optional): The role required to execute the command. Defaults to ''.

    This function creates an appropriate error message based on the type of error that occurred and sends it as a response to the user. If the error is not a UsageError or MissingRole, it also logs the error details in the guild's log.
    """
    def create_app_command_error_msg(error: discord.app_commands.AppCommandError, required_role: str) -> str:
        match error:
            case discord.app_commands.MissingRole():
                return failure_response(f"Du musst die Rolle '{required_role}' haben, um diesen Befehl zu benutzen.")
            case CodeError():
                return failure_response("Ein interner Fehler ist aufgetreten.", error=error)
            case UsageError():
                return failure_response(str(error))
            case _:
                return failure_response("Ein unbekannter Fehler ist aufgetreten.", error=error)

    msg = create_app_command_error_msg(error, reqired_role)
    if interaction.guild and not isinstance(error, UsageError) and not isinstance(error, app_commands.MissingRole):
        await log(interaction.guild, msg, details={'Command': command_name, 'Used by': f'{interaction.user.mention}'})
    await send_safe_response(interaction, msg, ephemeral=True)


# endregion


# region Roles

def get_student_role(guild: discord.Guild) -> discord.Role:
    """
    Retrieves the 'Schüler' role from the given Discord guild.

    Args:
        guild (discord.Guild): The Discord guild from which to retrieve the role.

    Returns:
        discord.Role: The role object corresponding to 'Schüler' in the guild.
    """
    return __unwrapped_get(guild.roles, 'Schüler')


def is_student(member: discord.Member) -> bool:
    """
    Checks if the given Discord member has the 'Schüler' role.

    Args:
        member (discord.Member): The Discord member to check.

    Returns:
        bool: True if the member has the 'Schüler' role, False otherwise.
    """
    return get_student_role(member.guild) in member.roles


def get_teacher_role(guild: discord.Guild) -> discord.Role:
    """
    Retrieves the 'Lehrer' role from the given Discord guild.

    Args:
        guild (discord.Guild): The Discord guild from which to retrieve the role.

    Returns:
        discord.Role: The role object corresponding to 'Lehrer' in the guild.
    """
    return __unwrapped_get(guild.roles, 'Lehrer')


def is_teacher(member: discord.Member) -> bool:
    """
    Checks if the given Discord member has the 'Lehrer' role.

    Args:
        member (discord.Member): The Discord member to check.

    Returns:
        bool: True if the member has the 'Lehrer' role, False otherwise.
    """
    return get_teacher_role(member.guild) in member.roles


def get_admin_role(guild: discord.Guild) -> discord.Role:
    """
    Retrieves the 'Admin' role from the given Discord guild.

    Args:
        guild (discord.Guild): The Discord guild from which to retrieve the role.

    Returns:
        discord.Role: The role object corresponding to 'Admin' in the guild.
    """
    return __unwrapped_get(guild.roles, 'Admin')


def is_admin(member: discord.Member) -> bool:
    """
    Checks if the given Discord member has the 'Admin' role.

    Args:
        member (discord.Member): The Discord member to check.

    Returns:
        bool: True if the member has the 'Admin' role, False otherwise.
    """
    return get_admin_role(member.guild) in member.roles

# endregion


# region Channels

def get_archive_channel(guild: discord.Guild) -> discord.CategoryChannel:
    """
    Retrieves the 'Archiv' category from the given Discord guild.

    Args:
        guild (discord.Guild): The Discord guild from which to retrieve the category.

    Returns:
        discord.CategoryChannel: The category object corresponding to 'Archiv' in the guild.
    """
    return __unwrapped_get(guild.categories, '📚 Wissensbereich')


def get_log_channel(guild: discord.Guild) -> discord.TextChannel:
    """
    Retrieves the 'logs' channel from the given Discord guild.

    Args:
        guild (discord.Guild): The Discord guild from which to retrieve the channel.

    Returns:
        discord.TextChannel: The channel object corresponding to 'logs' in the guild.
    """
    return __unwrapped_get(guild.text_channels, 'logs')


def generate_student_channel_name(student_name: str):
    """
    Generates a channel name for a student based on their real name.

    Args:
        student_name (str): The real name of the student.

    Returns:
        str: The generated channel name
    """
    return student_name.lower().replace(' ', '-')

# endregion


# region Members

def get_member(guild: discord.Guild, id: int) -> discord.Member:
    """
    Retrieves the Discord member with the given ID from the given guild.

    Args:
        guild (discord.Guild): The Discord guild from which to retrieve the member.
        id (int): The ID of the member to retrieve.

    Returns:
        discord.Member: The member object corresponding to the ID in the guild.
    """
    if result := discord.utils.get(guild.members, id=id):
        return result
    raise CodeError(f'Member with ID {id} not found')


def generate_member_nick(db_member: User) -> str:
    """
    Generates a nickname for a member based on their real name and icon.

    Args:
        db_member (User): The database user object representing the member.

    Returns:
        str: The generated nickname
    """
    return f'{'🎓' if db_member.is_teacher else '🎒' if db_member.is_student else '👋'} {db_member.real_name}'

# endregion


# region Response Message Generation

def success_response(msg: str) -> str:
    """
    Generates a success response message.

    Args:
        msg (str): The message to include in the response.

    Returns:
        str: The formatted success response message.
    """
    return f'✅ {msg}'


def failure_response(msg: str, error=None) -> str:  # TODO: Automated error logging, especially for CodeError
    """
    Generates a failure response message.

    Args:
        msg (str): The message to include in the response.
        error (Optional[Exception]): An optional error object to include in the response.
        Defaults to None.

    Returns:
        str: The formatted failure response message.
    """
    match error:
        case CodeError():
            return f'⚠️ **[DEV]** Es trat ein Fehler auf: {msg} ```{error}```'
        case None:
            return f'❌ {msg}'
        case _:
            return f'❌ Es trat ein Fehler auf: ```{error}```'

# endregion
