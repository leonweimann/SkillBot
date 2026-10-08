from collections import Counter
from typing import Iterator, Optional

import discord

from Utils.channel_moves import retry_transient
from Utils.database import Archive
from Utils.errors import CodeError


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

    _MAX_CAPACITY = 50  # Maximum number of channels in an archive category

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

        This method is limited to generating names for up to 36 unique categories
        (9 counts for each of 4 base icons).
        Since the capacity of archive categories is 50, this should suffice.

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

        for count in range(1, 10):  # Limit to 9 * 4 = 36 attempts to find a unique name
            for base_icon, base_name in zip(BASE_ICONS, BASE_NAMES):
                name = f"{base_icon} {base_name}" if count == 1 else f"{base_icon} {base_name} {count}"
                if name not in current_names:
                    return name

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
        all_archives = Archive.get_all(guild.id)
        for archive in all_archives:
            category = discord.utils.get(guild.categories, id=archive.id)
            if category and len(category.channels) < ArchiveCategory._MAX_CAPACITY:
                return category

        # If no suitable archive category is found, create a new one
        return await ArchiveCategory._create_new_archive_category(guild)

    @staticmethod
    async def _create_new_archive_category(guild: discord.Guild) -> discord.CategoryChannel:
        """
        Creates a new archive category in the specified guild.

        This method generates a unique name for the archive category and checks if a category with that
        name already exists. If not, it creates a new category in Discord. Either way the category is
        recorded in the database.

        Args:
            guild (discord.Guild): The Discord guild in which to create the archive category.

        Returns:
            discord.CategoryChannel: The newly created (or reused and now registered) archive category.

        Raises:
            CodeError: If an error occurs while creating the archive category.
        """
        # Generate a unique name
        name = ArchiveCategory._generate_name(guild.id)

        # Try to find an existing category with the same name
        new_category = discord.utils.get(guild.categories, name=name)
        # If no existing category is found, create a new one
        if not new_category:
            new_category = await guild.create_category(name=name)

        # Register in the database. A reused category with the generated name is not registered yet
        # (generated names never collide with registered ones); without a row it would never be
        # capacity-checked or treated as an archive.
        Archive(guild.id, new_category.id).edit(name=name)

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

    def can_add(self, channel: discord.TextChannel) -> bool:
        """
        Checks if a channel can be added to the archive category.

        This method verifies if the specified channel is not already in the archive category
        and if the category has space for more channels.

        Args:
            channel (discord.TextChannel): The channel to check.´

        Returns:
            bool: True if the channel can be added, False otherwise.
        """
        return channel not in self.category.channels and len(self.category.channels) < ArchiveCategory._MAX_CAPACITY

    async def add_channel(self, channel: discord.TextChannel) -> discord.CategoryChannel:
        """
        Adds a channel to the archive category if it can be added.

        This method checks if the channel can be added to the archive category and then
        moves the channel to the archive category if possible.

        Args:
            channel (discord.TextChannel): The channel to add to the archive category.

        Returns:
            discord.CategoryChannel: The archive category the channel was moved into.

        Raises:
            CodeError: If the channel is already in the archive category or if the category is full.
        """
        if self.can_add(channel):
            # Connect channel to this archive category
            await channel.edit(category=self.category)
            return self.category
        else:
            # Create new archive and add the channel there
            new_archive = await ArchiveCategory.make(self.guild)
            if new_archive.can_add(channel):
                # Connect to new archive category
                await channel.edit(category=new_archive.category)
                return new_archive.category
            else:
                # If this archive and an new archive cannot add the channel, raise an error
                raise CodeError(
                    f"Cannot add channel `{channel.name}` to archive category `{self.name}` or newly configured`{new_archive.name}`. "
                    "Either the channel is already in the archive or the archive is full."
                )

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


def is_category_full_error(error: BaseException) -> bool:
    """
    Checks whether a failed channel move was rejected because the target category is full.

    Discord answers such a move with ``400 Bad Request`` and JSON error code 50035 (Invalid Form Body),
    the nested error sits on the ``parent_id`` field ("Maximum number of channels in category reached
    (50)"). discord.py keeps the nested errors in ``_errors`` and flattens them into ``text``.

    Args:
        error (BaseException): The error raised by ``channel.edit(category=...)``.

    Returns:
        bool: True if the error says that the target category has no free slot.
    """
    if not isinstance(error, discord.HTTPException) or error.status != 400:
        return False
    text = (getattr(error, 'text', '') or '').lower()
    if 'maximum number of channels in category' in text:
        return True
    nested = getattr(error, '_errors', None)
    on_parent = (isinstance(nested, dict) and 'parent_id' in nested) or 'parent_id' in text
    return getattr(error, 'code', 0) == 50035 and on_parent


class ArchiveAllocator:
    """
    Distributes channels over the archive categories of a guild without exceeding Discord's limit.

    The guild cache (``category.channels``) is only updated when the gateway event of a move has been
    processed, which can happen after ``channel.edit`` returned. Picking an archive from the cache during a
    burst of moves can therefore choose an archive that is already full. The allocator instead fetches the
    channels once from the API (server truth), counts the channels per registered archive category and
    keeps that count up to date locally for every move it makes.

    If Discord still rejects a move because the archive is full (someone else filled it after the fetch),
    the archive is marked full and the channel goes to the next archive or a newly created one.

    Build one allocator per batch of moves and hold the guild lock (``Utils.channel_moves.get_guild_lock``)
    while using it, so no other move of the bot changes the counts in between.
    """

    MAX_FULL_RETRIES = 5     # Archives a single channel may be rejected by before giving up
    MAX_NEW_ARCHIVES = 3     # New archives a single pick may create (a reused one may already be full)

    def __init__(self, guild: discord.Guild, archives: list[discord.CategoryChannel], counts: Counter,
                 parents: dict[int, Optional[int]]):
        """
        Initializes the allocator. Use `ArchiveAllocator.create` to build it from the API.

        Args:
            guild (discord.Guild): The guild whose archives are used.
            archives (list[discord.CategoryChannel]): The existing archive categories in database order.
            counts (Counter): category_id -> number of channels in that category.
            parents (dict[int, Optional[int]]): channel_id -> category_id of every channel.
        """
        self.guild = guild
        self._archives = archives
        self._counts = counts
        self._parents = parents

    @classmethod
    async def create(cls, guild: discord.Guild) -> 'ArchiveAllocator':
        """
        Builds an allocator from the guild's channels as currently stored by Discord.

        Every channel with a parent counts towards that category's capacity (Discord's limit of 50 applies
        to all channel types). Archive rows whose category does not exist anymore are ignored.

        Args:
            guild (discord.Guild): The guild whose archives are used.

        Returns:
            ArchiveAllocator: The allocator (one ``fetch_channels`` request).
        """
        fetched = await retry_transient(guild.fetch_channels)
        fetched_by_id = {channel.id: channel for channel in fetched}
        counts: Counter = Counter()
        parents: dict[int, Optional[int]] = {}
        for channel in fetched:
            parent = getattr(channel, 'category_id', None)
            parents[channel.id] = parent
            if parent is not None:
                counts[parent] += 1

        archives: list[discord.CategoryChannel] = []
        for db_archive in Archive.get_all(guild.id):
            fetched_category = fetched_by_id.get(db_archive.id)
            if fetched_category is None:
                continue  # Deleted on Discord
            # Prefer the cached object (complete state), the fetched one is equivalent for moves
            archives.append(discord.utils.get(guild.categories, id=db_archive.id) or fetched_category)
        return cls(guild, archives, counts, parents)

    @property
    def archives(self) -> list[discord.CategoryChannel]:
        """The known archive categories in database order (including the ones created by this allocator)."""
        return list(self._archives)

    def count(self, category_id: int) -> int:
        """Returns the number of channels the allocator assumes in the given category."""
        return self._counts[category_id]

    def _is_archive(self, category_id: Optional[int]) -> bool:
        return category_id is not None and any(archive.id == category_id for archive in self._archives)

    async def pick(self) -> discord.CategoryChannel:
        """
        Returns the first archive with a free slot, creating a new archive if all are full.

        Returns:
            discord.CategoryChannel: An archive category with fewer than 50 channels (as far as known).

        Raises:
            CodeError: If no archive with a free slot could be found or created.
        """
        for archive in self._archives:
            if self._counts[archive.id] < ArchiveCategory._MAX_CAPACITY:
                return archive

        for _ in range(self.MAX_NEW_ARCHIVES):
            # Keep the returned object: the cache only knows the category once its gateway event arrived
            category = await ArchiveCategory._create_new_archive_category(self.guild)
            if not self._is_archive(category.id):
                self._archives.append(category)
            if self._counts[category.id] < ArchiveCategory._MAX_CAPACITY:
                return category

        raise CodeError("Kein Archiv mit freiem Platz gefunden und kein neues Archiv anlegbar")

    async def archive(self, channel: discord.abc.GuildChannel, *, reason: Optional[str] = None) -> discord.CategoryChannel:
        """
        Moves a channel into an archive category with a free slot.

        A transient error (network, 5xx) is retried once. If Discord rejects the move because the archive
        is full, that archive is marked full and the next one (or a new one) is tried. A channel that already
        is in an archive is not moved.

        Args:
            channel (discord.abc.GuildChannel): The channel to archive.
            reason (Optional[str]): The audit log reason.

        Returns:
            discord.CategoryChannel: The archive category the channel is in now.

        Raises:
            discord.HTTPException: If the move failed for another reason, or every tried archive was full.
            CodeError: If no archive with a free slot could be found or created.
        """
        current_parent = self._parents.get(channel.id, getattr(channel, 'category_id', None))
        if self._is_archive(current_parent):
            return next(archive for archive in self._archives if archive.id == current_parent)

        last_error: Optional[discord.HTTPException] = None
        for _ in range(self.MAX_FULL_RETRIES + 1):
            category = await self.pick()
            try:
                await retry_transient(lambda target=category: channel.edit(category=target, reason=reason))
            except discord.HTTPException as e:
                if not is_category_full_error(e):
                    raise
                print(f'[archive] Archive {category.id} is full on Discord, trying the next one: {e}')
                self._counts[category.id] = ArchiveCategory._MAX_CAPACITY
                last_error = e
                continue

            self._counts[category.id] += 1
            if current_parent is not None:
                self._counts[current_parent] = max(0, self._counts[current_parent] - 1)
            self._parents[channel.id] = category.id
            return category

        assert last_error is not None
        raise last_error
