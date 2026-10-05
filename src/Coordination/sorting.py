import discord

from Utils.archive import ArchiveCategory
import Utils.database as db


def ordered_channels(channels) -> list:
    """
    Returns the given channels in their target order.

    The channel named 'cmd' (if present) comes first, all other channels follow
    alphabetically by their lowercase name. Equal names are ordered by their id
    so the result is deterministic.

    Args:
        channels: Iterable of channel-like objects with `id` and `name` attributes.

    Returns:
        list: The channels in sorted order.
    """
    return sorted(channels, key=lambda c: (c.name != 'cmd', c.name.lower(), c.id))


def build_position_payload(ordered) -> list[dict]:
    """
    Builds the payload for a bulk channel position update.

    Every channel gets the position of its index in `ordered`. Only channels whose
    current position differs from their target position are included.

    Args:
        ordered: Channel-like objects (with `id` and `position`) in their target order.

    Returns:
        list[dict]: Entries of the form `{"id": int, "position": int}`.
    """
    return [
        {"id": channel.id, "position": index}
        for index, channel in enumerate(ordered)
        if channel.position != index
    ]


class ChannelSortingCoordinator:
    __debug_mode = False

    def activate_debug_mode(self):
        """
        Activates the debug mode.
        """
        self.__debug_mode = True
        print('[ChannelSortingManager] Debug mode activated')

    def _debug_log(self, message: str):
        """
        Logs a message if the debug mode is activated.
        """
        if self.__debug_mode:
            print(f'[ChannelSortingManager] {message}')

    @staticmethod
    def _is_allowed_category(category: discord.CategoryChannel) -> bool:
        """
        Check if the channel is allowed to be sorted.
        """
        allowed_categories_ids = db.DatabaseManager.get_all_teaching_categories(category.guild.id)
        for archive in ArchiveCategory.get_all(category.guild):
            allowed_categories_ids.append(archive.id)

        return category.id in allowed_categories_ids

    @staticmethod
    async def _bulk_update_positions(guild: discord.Guild, payload: list[dict], reason: str | None = None):
        """
        Updates the positions of multiple channels with a single request.

        Note:
            discord.py offers no public bulk position API (`channel.edit(position=...)` renumbers
            the whole guild from a possibly stale cache), so the private HTTP client is used here.
            discord.py is pinned in requirements.txt to keep this call stable.
        """
        await guild._state.http.bulk_channel_update(guild.id, payload, reason=reason)

    async def sort_channels_in_category(self, category: discord.CategoryChannel):
        """
        Sorts the channels within a given Discord category alphabetically by their name,
        with a specific channel named 'cmd' (if present) placed at the top.

        Args:
            category (discord.CategoryChannel): The Discord category whose channels
                                                 are to be sorted.

        Returns:
            None

        Behavior:
            - Skips sorting if the category is not allowed (based on `_is_allowed_category`).
            - Fetches fresh channel data from the API instead of relying on the cache.
            - Sorts the text channels of the category with `ordered_channels`.
            - Sends a single bulk position update for all channels whose position
              does not match the sorted order (nothing is sent if all are in place).
            - Logs debug information about the sorting process and any position updates.

        Note:
            This method is asynchronous and should be awaited when called.
        """
        if not self._is_allowed_category(category):
            self._debug_log(f'Skipping sorting for category {category.name} ({category.id})')
            return

        self._debug_log(f'Sorting channels in category {category.name} ({category.id})')

        guild = category.guild
        channels = [
            c for c in await guild.fetch_channels()
            if isinstance(c, discord.TextChannel) and c.category_id == category.id
        ]

        ordered = ordered_channels(channels)
        payload = build_position_payload(ordered)

        if not payload:
            self._debug_log(f'No need to update channels in category {category.name} ({category.id})')
            return

        for index, channel in enumerate(ordered):
            if channel.position != index:
                self._debug_log(f'Updating {channel.name} to position {index} (current: {channel.position})')

        await self._bulk_update_positions(guild, payload, reason=f'Sort channels in category {category.name}')


channel_sorting_coordinator = ChannelSortingCoordinator()
