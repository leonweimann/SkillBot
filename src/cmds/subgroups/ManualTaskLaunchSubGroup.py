import discord
from discord import app_commands

import Utils.environment as env
from Utils.notifications import NotificationManager


@app_commands.guild_only()
class ManualTaskLaunchSubGroup(app_commands.Group):
    """
    Subgroup for task management commands.

    This subgroup provides commands to manually launch tasks or check their status.
    It is intended for use by developers or administrators who need to control
    task execution without relying on automatic scheduling.
    """

    def __init__(self):
        super().__init__(
            name="tasks",
            description="Task management commands, that can be used to manually launch tasks or check their status."
        )

    @app_commands.command(
        name="db_integrity",
        description="Manually trigger a database integrity check"
    )
    @app_commands.checks.has_role('Dev')
    async def database_integrity(self, interaction: discord.Interaction):
        ...
