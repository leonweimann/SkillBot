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
        Sorts the channels in the given list by their name.
        The cmd channel is always the first channel in the list.
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
channel_sorting_coordinator.activate_debug_mode()
