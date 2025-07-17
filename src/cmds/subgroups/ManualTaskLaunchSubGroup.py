import discord
from discord import app_commands
from discord.ext import commands

import Utils.environment as env
from Utils.notifications import NotificationManager
from cogs.DatabaseIntegrity import DatabaseIntegrity


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
        """
        Manually trigger a database integrity check for the current guild.

        This command will run the same integrity checks that are normally
        performed automatically on a weekly basis.
        """
        # Defer the response since integrity checks can take some time
        await interaction.response.defer()

        # Check if this is in a guild
        if interaction.guild is None:
            await interaction.followup.send(
                "❌ **Error**: This command can only be used in a server."
            )
            return

        try:
            # Get the DatabaseIntegrity cog
            bot = interaction.client
            if not isinstance(bot, commands.Bot):
                await interaction.followup.send(
                    "❌ **Error**: Client is not a Bot instance."
                )
                await NotificationManager.send_system_error(
                    guild=interaction.guild,
                    component="ManualTaskLaunch",
                    error_message="Manual DB integrity check failed - Client is not a Bot instance",
                    context_user_id=interaction.user.id
                )
                return

            db_integrity_cog = bot.get_cog('DatabaseIntegrity')

            if db_integrity_cog is None:
                await interaction.followup.send(
                    "❌ **Error**: DatabaseIntegrity cog is not loaded."
                )
                await NotificationManager.send_system_error(
                    guild=interaction.guild,
                    component="ManualTaskLaunch",
                    error_message="Manual DB integrity check failed - DatabaseIntegrity cog not loaded",
                    context_user_id=interaction.user.id
                )
                return

            if not isinstance(db_integrity_cog, DatabaseIntegrity):
                await interaction.followup.send(
                    "❌ **Error**: DatabaseIntegrity cog is not the expected type."
                )
                await NotificationManager.send_system_error(
                    guild=interaction.guild,
                    component="ManualTaskLaunch",
                    error_message="Manual DB integrity check failed - DatabaseIntegrity cog type mismatch",
                    context_user_id=interaction.user.id
                )
                return

            # Log the start of manual integrity check
            await NotificationManager.send_success_notification(
                guild=interaction.guild,
                component="ManualTaskLaunch",
                message=f"Manual database integrity check initiated by {interaction.user.display_name} ({interaction.user.id})"
            )

            # Run the manual integrity check
            result = await db_integrity_cog.run_manual_integrity_check(interaction.guild)

            if result['success']:
                await interaction.followup.send(
                    "✅ **Database Integrity Check Completed**\n"
                    "The manual integrity check has been completed successfully. "
                    "Check the system notifications for detailed results."
                )
                await NotificationManager.send_success_notification(
                    guild=interaction.guild,
                    component="ManualTaskLaunch",
                    message=f"Manual database integrity check completed successfully (initiated by {interaction.user.display_name})"
                )
            else:
                error_msg = result.get('error_message', 'Unknown error occurred')
                await interaction.followup.send(
                    f"❌ **Database Integrity Check Failed**\n"
                    f"Error: {error_msg}"
                )
                await NotificationManager.send_system_error(
                    guild=interaction.guild,
                    component="ManualTaskLaunch",
                    error_message="Manual database integrity check failed",
                    error_details=error_msg,
                    context_user_id=interaction.user.id
                )

        except Exception as e:
            await interaction.followup.send(
                f"❌ **Unexpected Error**\n"
                f"An unexpected error occurred while running the integrity check: {str(e)}"
            )
            await NotificationManager.send_system_error(
                guild=interaction.guild,
                component="ManualTaskLaunch",
                error_message="Manual database integrity check failed with unexpected error",
                error_details=str(e),
                context_user_id=interaction.user.id
            )
