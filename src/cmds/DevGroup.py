import discord
from discord import app_commands

import Utils.environment as env
from Utils.database import DevMode
from Utils.notifications import NotificationManager


@app_commands.guild_only()
class DevGroup(app_commands.Group):
    """
    Command group for developer mode management.

    This group provides commands for developers to control
    their personal notification settings.
    """

    def __init__(self):
        super().__init__(
            name="dev",
            description="Developer mode commands"
        )

    @app_commands.command(
        name="on",
        description="Enable developer mode for yourself"
    )
    @app_commands.checks.has_role('Dev')
    async def dev_on(self, interaction: discord.Interaction):
        """
        Enable developer mode for yourself.

        When enabled, you'll receive system notifications in your cmd channel.
        """
        if not interaction.guild:
            await interaction.response.send_message(
                "❌ This command can only be used in a server."
            )
            return

        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "❌ This command can only be used by server members."
            )
            return

        # Check if user is a teacher (required for cmd channel access)
        if not env.is_teacher(interaction.user):
            await interaction.response.send_message(
                "❌ You must be a teacher to use developer mode (cmd channel required)."
            )
            return

        try:
            # Enable dev mode for this user
            DevMode.set_dev_mode(interaction.guild.id, interaction.user.id, True)

            embed = discord.Embed(
                title="🔧 Developer Mode Enabled",
                description="You will now receive system notifications in your cmd channel.",
                color=discord.Color.green()
            )

            embed.add_field(
                name="What's Next?",
                value="• System alerts will be sent to your cmd channel\n• You'll be mentioned for critical issues\n• Use `/dev off` to disable notifications",
                inline=False
            )

            await interaction.response.send_message(embed=embed)

        except Exception as e:
            embed = discord.Embed(
                title="❌ Failed to Enable Developer Mode",
                description=f"An error occurred: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed)

    @dev_on.error
    async def dev_on_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        await env.handle_app_command_error(
            interaction, error, command_name="dev on", reqired_role="Dev"
        )

    @app_commands.command(
        name="off",
        description="Disable developer mode for yourself"
    )
    @app_commands.checks.has_role('Dev')
    async def dev_off(self, interaction: discord.Interaction):
        """
        Disable developer mode for yourself.

        You'll no longer receive automatic system notifications.
        """
        if not interaction.guild:
            await interaction.response.send_message(
                "❌ This command can only be used in a server."
            )
            return

        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "❌ This command can only be used by server members."
            )
            return

        try:
            # Disable dev mode for this user
            DevMode.set_dev_mode(interaction.guild.id, interaction.user.id, False)

            embed = discord.Embed(
                title="🔧 Developer Mode Disabled",
                description="You will no longer receive automatic system notifications.",
                color=discord.Color.orange()
            )

            embed.add_field(
                name="Note",
                value="You can re-enable notifications anytime with `/dev on`",
                inline=False
            )

            await interaction.response.send_message(embed=embed)

        except Exception as e:
            embed = discord.Embed(
                title="❌ Failed to Disable Developer Mode",
                description=f"An error occurred: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed)

    @dev_off.error
    async def dev_off_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        await env.handle_app_command_error(
            interaction, error, command_name="dev off", reqired_role="Dev"
        )

    @app_commands.command(
        name="status",
        description="Check your developer mode status and see other active developers"
    )
    @app_commands.checks.has_role('Dev')
    async def dev_status(self, interaction: discord.Interaction):
        """
        Check developer mode status for yourself and see other active developers.
        """
        if not interaction.guild:
            await interaction.response.send_message(
                "❌ This command can only be used in a server."
            )
            return

        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "❌ This command can only be used by server members."
            )
            return

        try:
            # Check user's own status
            user_status = DevMode.is_dev_mode_active(interaction.guild.id, interaction.user.id)
            status_text = "**Enabled** ✅" if user_status else "**Disabled** ❌"

            embed = discord.Embed(
                title="🔧 Developer Mode Status",
                description=f"Your status: {status_text}",
                color=discord.Color.green() if user_status else discord.Color.red()
            )

            # Get all active dev users
            active_dev_user_ids = DevMode.get_active_dev_users(interaction.guild.id)
            active_devs = []

            for user_id in active_dev_user_ids:
                member = interaction.guild.get_member(user_id)
                if member and env.is_dev(member):
                    active_devs.append(member)

            if active_devs:
                dev_list = "\n".join([f"• {member.mention}" for member in active_devs[:10]])
                if len(active_devs) > 10:
                    dev_list += f"\n• ... and {len(active_devs) - 10} more"
                embed.add_field(
                    name=f"Active Developers ({len(active_devs)})",
                    value=dev_list,
                    inline=False
                )
            else:
                embed.add_field(
                    name="Active Developers",
                    value="No developers currently have notifications enabled",
                    inline=False
                )

            # All dev members
            all_dev_members = [member for member in interaction.guild.members if env.is_dev(member)]
            embed.add_field(
                name="Total Dev Members",
                value=str(len(all_dev_members)),
                inline=True
            )

            await interaction.response.send_message(embed=embed)

        except Exception as e:
            embed = discord.Embed(
                title="❌ Failed to Check Status",
                description=f"An error occurred: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed)

    @dev_status.error
    async def dev_status_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        await env.handle_app_command_error(
            interaction, error, command_name="dev status", reqired_role="Dev"
        )

    @app_commands.command(
        name="test-alert",
        description="Send a test notification to verify the notification system"
    )
    @app_commands.checks.has_role('Dev')
    async def test_alert(self, interaction: discord.Interaction):
        """
        Send a test notification to verify all notification channels are working.
        """
        if not interaction.guild:
            await interaction.response.send_message(
                "❌ This command can only be used in a server."
            )
            return

        await interaction.response.defer()

        try:
            # Send test alert
            await NotificationManager.send_integrity_alert(
                bot=interaction.client,
                issue_type="Test Alert",
                component="DevGroup",
                total_issues=1,
                details=f"Test notification triggered by {interaction.user.mention}",
                context_user_id=interaction.user.id
            )

            embed = discord.Embed(
                title="✅ Test Alert Sent",
                description="Check the logs, alerts, and cmd channels to verify notifications are working.",
                color=discord.Color.green()
            )

        except Exception as e:
            embed = discord.Embed(
                title="❌ Test Alert Failed",
                description=f"Failed to send test alert: {str(e)}",
                color=discord.Color.red()
            )

        await interaction.followup.send(embed=embed)

    @test_alert.error
    async def test_alert_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        await env.handle_app_command_error(
            interaction, error, command_name="dev test-alert", reqired_role="Dev"
        )


async def setup(bot):
    bot.tree.add_command(
        DevGroup()
    )
    print('[Group] DevGroup loaded')
