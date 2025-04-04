import discord

import Utils.database as db
import Utils.environment as env


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
        allowed_categories_ids.append(env.get_archive_channel(category.guild).id)

        return category.id in allowed_categories_ids

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
            - Sorts channels alphabetically by their lowercase names.
            - Ensures the channel named 'cmd' (if it exists) is placed at the top of the list.
            - Updates the position of each channel in the category if their current position
              does not match the sorted order.
            - Logs debug information about the sorting process and any position updates.

        Note:
            This method is asynchronous and should be awaited when called.
        """
        if not self._is_allowed_category(category):
            self._debug_log(f'Skipping sorting for category {category.name} ({category.id})')
            return

        # Sort the channels by their name
        sorted_channels = sorted(category.channels, key=lambda c: c.name.lower())

        cmd_channel = discord.utils.get(category.channels, name='cmd')
        if cmd_channel:
            sorted_channels.remove(cmd_channel)
            sorted_channels.insert(0, cmd_channel)

        self._debug_log(f'Sorting channels in category {category.name} ({category.id})')

        # Update the position of each channel
        for index, channel in enumerate(sorted_channels):
            if channel.position != index:
                self._debug_log(f'Updating {channel.name} to position {index} (current: {channel.position})')
                await channel.edit(position=index)
            else:
                self._debug_log(f'No need to update {channel.name} (current: {channel.position})')


channel_sorting_coordinator = ChannelSortingCoordinator()
