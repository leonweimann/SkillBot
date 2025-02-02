from discord import *


async def setup_server(guild: Guild):
    """
    Sets up the server with predefined roles, categories, channels, and permissions.

    This function performs the following tasks:
    1. Creates roles for students, teachers, and admins if they do not already exist.
    2. Creates categories for information, text channels, and voice channels if they do not already exist.
    3. Creates text and voice channels within the respective categories if they do not already exist.
    4. Configures permissions for the default role (@everyone), student role, teacher role, and admin role.
    5. Sets specific permissions for the newly created channels to control access and actions for different roles.
    6. Configures server settings such as default notifications and system channel.

    Args:
        guild (Guild): The guild (server) where the setup will be performed.
    """

    # Create anything

    student_role = await __create_role_if_not_exists(guild, 'Schüler', Color.greyple())
    teacher_role = await __create_role_if_not_exists(guild, 'Lehrer', Color.blue())
    admin_role = await __create_role_if_not_exists(guild, 'Admin', Color.orange())

    information_category = await __create_category_if_not_exists(guild, 'Informationen')
    text_category = await __create_category_if_not_exists(guild, 'Textkanäle')
    voice_category = await __create_category_if_not_exists(guild, 'Sprachkanäle')
    await __create_category_if_not_exists(guild, '📚 Wissensbereich')

    new_members_channel = await __create_text_channel_if_not_exists(guild, 'neue-mitglieder', information_category)

    general_channel = await __create_text_channel_if_not_exists(guild, 'allgemein', text_category)
    teacher_chat_channel = await __create_text_channel_if_not_exists(guild, 'lehrer-chat', text_category)

    logs_channel = await __create_text_channel_if_not_exists(guild, 'logs', information_category)

    lounge_voice_channel = await __create_voice_channel_if_not_exists(guild, 'lounge', voice_category)
    classroom_voice_channel = await __create_voice_channel_if_not_exists(guild, 'klassenzimmer', voice_category)

    # Configure anything

    await guild.default_role.edit(permissions=Permissions())  # Block anything for default members / @everyone

    await student_role.edit(
        permissions=Permissions(
            add_reactions=True,
            attach_files=True,
            connect=True,
            embed_links=True,
            read_messages=True,
            read_message_history=True,
            send_messages=True,
            speak=True,
            stream=True,
            use_application_commands=True,
            view_channel=True
        )
    )

    await teacher_role.edit(
        permissions=Permissions(
            add_reactions=True,
            attach_files=True,
            connect=True,
            embed_links=True,
            manage_messages=True,
            mention_everyone=True,
            move_members=True,
            mute_members=True,
            read_messages=True,
            read_message_history=True,
            send_messages=True,
            speak=True,
            stream=True,
            use_application_commands=True,
            view_channel=True
        )
    )

    await admin_role.edit(permissions=Permissions.all())

    await new_members_channel.edit(
        overwrites={
            guild.default_role: PermissionOverwrite(
                read_messages=True,
                read_message_history=True,
                view_channel=True
            ),
            student_role: PermissionOverwrite(
                view_channel=False  # No permissions for students -> hide
            ),
            teacher_role: PermissionOverwrite(
                view_channel=False  # No permissions for teachers -> hide
            )
        }
    )

    await general_channel.edit(
        overwrites={
            guild.default_role: PermissionOverwrite(
                read_messages=True,
                read_message_history=True,
                view_channel=True
            ),
            student_role: PermissionOverwrite(
                send_messages=False
            )
        }
    )

    await teacher_chat_channel.edit(
        overwrites={
            student_role: PermissionOverwrite(
                view_channel=False
            ),
            teacher_role: PermissionOverwrite(
                view_channel=True,
                manage_messages=False
            ),
            admin_role: PermissionOverwrite(
                view_channel=False
            )
        }
    )

    await logs_channel.edit(
        overwrites={
            guild.default_role: PermissionOverwrite(
                view_channel=False
            ),
            student_role: PermissionOverwrite(
                view_channel=False
            ),
            teacher_role: PermissionOverwrite(
                view_channel=False
            ),
            admin_role: PermissionOverwrite(
                send_messages=False,
                view_channel=True
            )
        }
    )

    await lounge_voice_channel.edit(
        overwrites={
            student_role: PermissionOverwrite(
                speak=False,
                stream=False
            )
        }
    )

    await classroom_voice_channel.edit(
        overwrites={
            student_role: PermissionOverwrite(
                view_channel=False
            )
        }
    )

    # Configure server settings

    await guild.edit(default_notifications=NotificationLevel.only_mentions, system_channel=general_channel)


async def __create_role_if_not_exists(guild: Guild, role_name: str, color: Color) -> Role:
    """
    Asynchronously creates a role in the specified guild if it does not already exist.

    Args:
        guild (Guild): The guild in which to create the role.
        role_name (str): The name of the role to create.
        color (Color): The color of the role to create.

    Returns:
        Role: The created or existing role.
    """

    role = utils.get(guild.roles, name=role_name)
    if role is None:
        role = await guild.create_role(name=role_name, color=color)
    return role


async def __create_category_if_not_exists(guild: Guild, category_name: str) -> CategoryChannel:
    """
    Asynchronously creates a category in the guild if it does not already exist.

    Args:
        guild (Guild): The guild in which to check or create the category.
        category_name (str): The name of the category to check or create.

    Returns:
        CategoryChannel: The existing or newly created category channel.
    """

    category = utils.get(guild.categories, name=category_name)
    if category is None:
        category = await guild.create_category(category_name)
    return category


async def __create_voice_channel_if_not_exists(guild: Guild, channel_name: str, category: CategoryChannel) -> VoiceChannel:
    """
    Asynchronously creates a voice channel in the specified guild if it does not already exist.

    Args:
        guild (Guild): The guild in which to create the voice channel.
        channel_name (str): The name of the voice channel to create.
        category (CategoryChannel): The category under which to create the voice channel.

    Returns:
        VoiceChannel: The created or existing voice channel.
    """

    channel = utils.get(guild.voice_channels, name=channel_name)
    if channel is None:
        channel = await category.create_voice_channel(channel_name)
    return channel


async def __create_text_channel_if_not_exists(guild: Guild, channel_name: str, category: CategoryChannel) -> TextChannel:
    """
    Asynchronously creates a text channel in the specified guild if it does not already exist.

    Args:
        guild (Guild): The guild in which to create the text channel.
        channel_name (str): The name of the text channel to create.
        category (CategoryChannel): The category under which to create the text channel.

    Returns:
        TextChannel: The created or existing text channel.
    """

    channel = utils.get(guild.text_channels, name=channel_name)
    if channel is None:
        channel = await category.create_text_channel(channel_name)
    return channel
