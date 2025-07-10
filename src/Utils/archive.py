from typing import Iterator

import discord

from database import Archive
from errors import CodeError


class ArchiveCategory:
    """
    ArchiveCategory provides utility methods for managing Discord archive categories within a guild.

    This class handles the creation and retrieval of archive categories, ensuring that each category
    has a unique name and does not exceed Discord's maximum channel limit per category. It interacts
    with both the Discord API and a database layer (via the Archive class) to maintain consistency
    between the server and persistent storage.

    Attributes:
        guild (discord.Guild): The Discord guild (server) associated with this instance.
        category (discord.CategoryChannel): The Discord category channel managed by this instance.
    """

    def __init__(self, guild: discord.Guild, category: discord.CategoryChannel):
        """
        Initializes the class with the specified Discord guild and category channel.

        Args:
            guild (discord.Guild): The Discord guild (server) associated with this instance.
            category (discord.CategoryChannel): The Discord category channel to be used.
        """
        self.guild = guild
        self.category = category

    def __repr__(self) -> str:
        return f"""
            ArchiveCategory(
                guild={self.guild.name}, {self.guild.id}, (Detail: {self.guild})
                category={self.category.name}, {self.category.id}, (Detail: {self.category}
            )
        """

    @classmethod
    async def make(cls, guild: discord.Guild) -> 'ArchiveCategory':
        """
        Makes an ArchiveCategory instance for the specified guild.

        This class method retrieves the current archive category for the guild.
        If there is no existing archive category, it creates a new one.

        Args:
            guild (discord.Guild): The guild for which to create the archive category.

        Returns:
            ArchiveCategory: An instance of ArchiveCategory for the specified guild.
        """
        category = await cls._get_current_archive(guild)
        return cls(guild, category)

    @staticmethod
    def _generate_name(guild_id: int) -> str:
        """
        Generates a unique name for an archive category based on predefined icons and names.

        This method checks existing archive categories in the database to ensure that the generated name
        does not conflict with any existing names. It uses a combination of base icons and names,
        appending a count if necessary to ensure uniqueness.

        Args:
            guild_id (int): The ID of the Discord guild for which to generate the name.

        Returns:
            str: A unique name for the archive category.

        Raises:
            CodeError: If a unique name cannot be generated after exhausting all options.
        """
        BASE_ICONS = ['📚', '🗃️', '🗄️', '📦']
        BASE_NAMES = ['Wissensbereich', 'Wissenskammer', 'Wissensspeicher', 'Lehrarchiv']

        current_names = list(map(
            lambda a: a.name if isinstance(a.name, str) else '',
            Archive.get_all(guild_id)
        ))

        for base_icon, base_name in zip(BASE_ICONS, BASE_NAMES):
            count = 1
            while True:
                name = f"{base_icon} {base_name}" if count == 1 else f"{base_icon} {base_name} {count}"
                if name not in current_names:
                    return name
                count += 1

        raise CodeError("Failed to generate a unique name for the archive category.")

    @staticmethod
    async def _get_current_archive(guild: discord.Guild) -> discord.CategoryChannel:
        """
        Retrieves the current archive category for the specified guild.

        This method checks existing archive categories in the guild and returns the first one that has
        fewer than the maximum allowed number of channels. If no suitable category is found, it creates
        a new archive category.

        Args:
            guild (discord.Guild): The Discord guild for which to retrieve the archive category.

        Returns:
            discord.CategoryChannel: The current archive category for the guild, or a newly created one if
            no suitable category exists.

        Raises:
            CodeError: If an error occurs while retrieving or creating the archive category.
        """
        _MAX_CHANNELS = 50  # Maximum number of channels in a category

        all_archives = Archive.get_all(guild.id)
        for archive in all_archives:
            category = discord.utils.get(guild.categories, id=archive.id)
            if category and len(category.channels) < _MAX_CHANNELS:
                return category

        # If no suitable archive category is found, create a new one
        return await ArchiveCategory._create_new_archive_category(guild)

    @staticmethod
    async def _create_new_archive_category(guild: discord.Guild) -> discord.CategoryChannel:
        """
        Creates a new archive category in the specified guild.

        This method generates a unique name for the archive category and checks if it already exists.
        If it does not exist, it creates a new category in Discord and records it in the database.

        Args:
            guild (discord.Guild): The Discord guild in which to create the archive category.

        Returns:
            discord.CategoryChannel: The newly created archive category channel.

        Raises:
            CodeError: If an error occurs while creating the archive category.
        """
        name = ArchiveCategory._generate_name(guild.id)  # Generate a unique name
        new_category = discord.utils.get(guild.categories, name=name)
        if not new_category:
            # Create in discord
            new_category = await guild.create_category(name=name)
            # Create in database
            db_archive = Archive(guild.id, new_category.id)
            db_archive.edit(name=name)
        return new_category

    @staticmethod
    def get_all(guild: discord.Guild) -> 'Iterator[ArchiveCategory]':
        """
        Retrieves all archive categories for the specified guild.

        This static method fetches all archive categories from the database and returns them as a list
        of ArchiveCategory instances.

        Args:
            guild_id (int): The ID of the Discord guild for which to retrieve archive categories.

        Returns:
            list[ArchiveCategory]: A list of ArchiveCategory instances for the specified guild.
        """
        for db_archive in Archive.get_all(guild.id):
            category = discord.utils.get(guild.categories, id=db_archive.id)
            if category:
                yield ArchiveCategory(guild, category)

    async def can_add(self, channel: discord.TextChannel) -> bool:
        """
        Checks if a channel can be added to the archive category.

        This method verifies if the specified channel is not already in the archive category
        and if the category has space for more channels.

        Args:
            channel (discord.TextChannel): The channel to check.

        Returns:
            bool: True if the channel can be added, False otherwise.
        """
        return channel not in self.category.channels and len(self.category.channels) < 50

    async def add_channel(self, channel: discord.TextChannel):
        """
        Adds a channel to the archive category if it can be added.

        This method checks if the channel can be added to the archive category and then
        moves the channel to the archive category if possible.

        Args:
            channel (discord.TextChannel): The channel to add to the archive category.

        Raises:
            CodeError: If the channel is already in the archive category or if the category is full.
        """
        if self.can_add(channel):
            await channel.edit(category=self.category)
        else:
            # Create new archive and add the channel there
            new_archive = await ArchiveCategory.make(self.guild)
            if new_archive.can_add(channel):
                await channel.edit(category=new_archive.category)
            else:
                raise CodeError(f"Cannot add channel {channel.name} to archive category {self.category.name}. "
                                "Either the channel is already in the archive or the archive is full.")

    @property
    def name(self) -> str:
        """
        Returns the name of the archive category.

        This property retrieves the name of the archive category managed by this instance.

        Returns:
            str: The name of the archive category.
        """
        return self.category.name

    @property
    def id(self) -> int:
        """
        Returns the ID of the archive category.

        This property retrieves the ID of the archive category managed by this instance.

        Returns:
            int: The ID of the archive category.
        """
        return self.category.id

    @property
    def channels(self) -> list[discord.TextChannel]:
        """
        Returns a list of channels in the archive category.

        This property retrieves all text channels that are currently in the archive category.

        Returns:
            list[discord.TextChannel]: A list of text channels in the archive category.
        """
        return self.category.text_channels


# if __name__ == "__main__":
#     import asyncio
#     from unittest.mock import MagicMock
#     from database import DatabaseManager

#     async def main():
#         DatabaseManager.create_tables(42)

#         mock_guild = MagicMock(spec=discord.Guild)
#         mock_guild.id = 42  # Example guild ID for testing

#         archive_category = await ArchiveCategory.create(mock_guild)
#         name = ArchiveCategory._generate_name(mock_guild.id)
#         print(f"Generated archive category name: {name}")

#     asyncio.run(main())
