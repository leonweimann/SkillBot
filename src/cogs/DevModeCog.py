import discord
from discord.ext import commands
from discord import app_commands

import Utils.environment as env
from Utils.notifications import NotificationManager


class DevModeCog(commands.Cog):
    """
    Cog for managing developer mode and notifications.

    This cog provides slash commands for developers to control
    the notification system and dev mode settings.
    """

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'[COG] {self.__class__.__name__} is ready')

    @app_commands.command(
        name="dev-mode",
        description="Enable or disable developer mode for notifications"
    )
    @app_commands.describe(
        action="Enable or disable dev mode"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="on", value="on"),
        app_commands.Choice(name="off", value="off"),
        app_commands.Choice(name="status", value="status")
    ])
    @app_commands.checks.has_any_role('Dev', 'Admin')
    async def dev_mode(self, interaction: discord.Interaction, action: str):
        """
        Control developer notification mode.

        When enabled, all developers with the 'Dev' role will receive
        system notifications in their cmd channels.
        """
        if not interaction.guild:
            await interaction.response.send_message(
                "❌ This command can only be used in a server.",
                ephemeral=True
            )
            return

        current_status = NotificationManager.is_dev_mode_enabled(interaction.guild.id)

        if action == "on":
            NotificationManager.set_dev_mode(interaction.guild.id, True)
            embed = discord.Embed(
                title="🔧 Developer Mode Enabled",
                description="All developers will now receive system notifications in their cmd channels.",
                color=discord.Color.green()
            )

        elif action == "off":
            NotificationManager.set_dev_mode(interaction.guild.id, False)
            embed = discord.Embed(
                title="🔧 Developer Mode Disabled",
                description="Developers will no longer receive automatic system notifications.",
                color=discord.Color.red()
            )

        else:  # status
            status_text = "**Enabled**" if current_status else "**Disabled**"
            embed = discord.Embed(
                title="🔧 Developer Mode Status",
                description=f"Current status: {status_text}",
                color=discord.Color.blue()
            )

            # Add info about dev members
            dev_members = [member for member in interaction.guild.members if env.is_dev(member)]
            if dev_members:
                dev_list = "\n".join([f"• {member.mention}" for member in dev_members[:10]])
                if len(dev_members) > 10:
                    dev_list += f"\n• ... and {len(dev_members) - 10} more"
                embed.add_field(
                    name="Developers",
                    value=dev_list,
                    inline=False
                )
            else:
                embed.add_field(
                    name="Developers",
                    value="No members with 'Dev' role found",
                    inline=False
                )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @dev_mode.error
    async def dev_mode_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        await env.handle_app_command_error(
            interaction, error, command_name="dev-mode", reqired_role="Dev or Admin"
        )

    @app_commands.command(
        name="test-alert",
        description="Send a test notification to verify the notification system"
    )
    @app_commands.checks.has_any_role('Dev', 'Admin')
    async def test_alert(self, interaction: discord.Interaction):
        """
        Send a test notification to verify all notification channels are working.
        """
        if not interaction.guild:
            await interaction.response.send_message(
                "❌ This command can only be used in a server.",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            # Send test alert
            await NotificationManager.send_integrity_alert(
                bot=self.bot,
                issue_type="Test Alert",
                component="DevMode",
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

        await interaction.followup.send(embed=embed, ephemeral=True)

    @test_alert.error
    async def test_alert_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        await env.handle_app_command_error(
            interaction, error, command_name="test-alert", reqired_role="Dev or Admin"
        )


async def setup(bot):
    await bot.add_cog(DevModeCog(bot))
