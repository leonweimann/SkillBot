import discord
from typing import Optional, List
from datetime import datetime

import Utils.environment as env
from Utils.database import DatabaseManager, Teacher, DevMode
from Utils.lwlogging import log


class NotificationManager:
    """
    Centralized notification system for sending alerts to developers and logging issues.

    This class provides a unified way to handle error notifications, integrity issues,
    and other system alerts. It supports detailed logging, alerts channel notifications,
    and selective developer notifications based on per-user dev mode settings.
    """

    @staticmethod
    async def send_system_alert(
        guild: discord.Guild,
        issue_type: str,
        component: str,
        total_issues: int,
        details: str,
        context_user_id: Optional[int] = None
    ):
        """
        Send an integrity issue alert to logs, alerts channel, and appropriate cmd channels.

        Args:
            guild: The specific guild to send the alert to
            issue_type: Type of integrity issue (e.g., "Orphaned Subusers")
            component: Component that detected the issue (e.g., "DatabaseIntegrity")
            total_issues: Total number of issues found
            details: Detailed description of the issues
            context_user_id: ID of user who triggered the check (optional)
        """
        try:
            # Send detailed log to the logs channel
            await NotificationManager._send_detailed_log(
                guild, issue_type, component, total_issues, details
            )

            # Send alert to alerts channel
            await NotificationManager._send_alerts_channel_notification(
                guild, issue_type, component, total_issues
            )

            # Send notifications to appropriate cmd channels
            await NotificationManager._send_cmd_notifications(
                guild, issue_type, component, total_issues, context_user_id
            )

        except Exception as e:
            print(f"[NotificationManager] Failed to send alerts for guild {guild.id}: {e}")

    @staticmethod
    async def _send_detailed_log(
        guild: discord.Guild,
        issue_type: str,
        component: str,
        total_issues: int,
        details: str
    ):
        """Send detailed log message to the guild's logs channel."""
        try:
            logs_channel = env.get_log_channel(guild)

            embed = discord.Embed(
                title="🚨 Database Integrity Issue Detected",
                color=discord.Color.red(),
                timestamp=datetime.utcnow()
            )

            embed.add_field(
                name="Issue Type",
                value=issue_type,
                inline=True
            )

            embed.add_field(
                name="Component",
                value=component,
                inline=True
            )

            embed.add_field(
                name="Total Issues",
                value=str(total_issues),
                inline=True
            )

            embed.add_field(
                name="Details",
                value=f"```\n{details[:1000]}{'...' if len(details) > 1000 else ''}\n```",
                inline=False
            )

            embed.set_footer(text="Action required: Manual review and cleanup needed")

            await logs_channel.send(embed=embed)

        except Exception as e:
            print(f"[NotificationManager] Failed to send detailed log: {e}")

    @staticmethod
    async def send_system_error(
        guild: discord.Guild,
        component: str,
        error_message: str,
        error_details: Optional[str] = None,
        context_user_id: Optional[int] = None
    ):
        """
        Send a system error notification.

        Args:
            guild: The specific guild to send the error to
            component: Component that encountered the error
            error_message: Brief error message
            error_details: Detailed error information
            context_user_id: ID of user who triggered the error (optional)
        """
        try:
            # Log to logs channel
            await log(
                guild,
                f"[ERROR] {component}: {error_message}",
                {"Details": error_details or "No additional details", "Component": component}
            )

            # Send alerts and cmd notifications
            await NotificationManager._send_alerts_channel_notification(
                guild, "System Error", component, 1
            )

            await NotificationManager._send_cmd_notifications(
                guild, "System Error", component, 1, context_user_id
            )

        except Exception as e:
            print(f"[NotificationManager] Failed to send error notification for guild {guild.id}: {e}")

    @staticmethod
    async def send_success_notification(
        guild: discord.Guild,
        component: str,
        message: str
    ):
        """
        Send a success notification to logs channel.

        Args:
            guild: The specific guild to send the notification to
            component: Component reporting success
            message: Success message
        """
        try:
            await log(
                guild,
                f"[SUCCESS] {component}: {message}",
                {"Component": component}
            )
        except Exception as e:
            print(f"[NotificationManager] Failed to send success notification for guild {guild.id}: {e}")

    @staticmethod
    async def _send_alerts_channel_notification(
        guild: discord.Guild,
        issue_type: str,
        component: str,
        total_issues: int
    ):
        """Send alert notification to the alerts channel."""
        try:
            alerts_channel = env.get_alerts_channel(guild)

            embed = discord.Embed(
                title="🚨 System Alert",
                color=discord.Color.orange(),
                timestamp=datetime.utcnow()
            )

            embed.add_field(
                name="Issue Type",
                value=issue_type,
                inline=True
            )

            embed.add_field(
                name="Component",
                value=component,
                inline=True
            )

            embed.add_field(
                name="Issues Found",
                value=str(total_issues),
                inline=True
            )

            embed.set_footer(text="Check logs channel for detailed information")

            await alerts_channel.send(embed=embed)

        except Exception as e:
            print(f"[NotificationManager] Failed to send alerts channel notification: {e}")

    @staticmethod
    async def _send_cmd_notifications(
        guild: discord.Guild,
        issue_type: str,
        component: str,
        total_issues: int,
        context_user_id: Optional[int] = None
    ):
        """Send notifications to cmd channels based on per-user dev mode settings."""
        try:
            # Get all dev members who have dev mode enabled
            dev_members = [member for member in guild.members if env.is_dev(member)]

            for dev_member in dev_members:
                # Only notify if this specific user has dev mode enabled
                if DevMode.is_dev_mode_active(guild.id, dev_member.id):
                    await NotificationManager._send_individual_cmd_notification(
                        guild, dev_member, issue_type, component, total_issues, is_dev=True
                    )

            # If there's a context user (who triggered the issue), notify them regardless of dev mode
            if context_user_id:
                context_member = guild.get_member(context_user_id)
                if context_member and env.is_teacher(context_member):
                    # If context user is not a dev, send them a notification
                    if not env.is_dev(context_member):
                        # Check if any dev users have dev mode active to know if dev team was informed
                        active_dev_users = DevMode.get_active_dev_users(guild.id)
                        dev_team_informed = len(active_dev_users) > 0

                        await NotificationManager._send_individual_cmd_notification(
                            guild, context_member, issue_type, component, total_issues,
                            is_dev=False, dev_team_informed=dev_team_informed
                        )

        except Exception as e:
            print(f"[NotificationManager] Failed to send cmd notifications: {e}")

    @staticmethod
    async def _send_individual_cmd_notification(
        guild: discord.Guild,
        member: discord.Member,
        issue_type: str,
        component: str,
        total_issues: int,
        is_dev: bool = False,
        dev_team_informed: bool = False
    ):
        """Send notification to an individual's cmd channel."""
        try:
            if not env.is_teacher(member):
                return

            db_teacher = Teacher(guild.id, member.id)
            if not db_teacher.teaching_category:
                return

            teacher_category = discord.utils.get(guild.categories, id=db_teacher.teaching_category)
            if not teacher_category:
                return

            cmd_channel = discord.utils.get(teacher_category.text_channels, name='cmd')
            if not cmd_channel:
                return

            # Compose message based on role
            if is_dev:
                message = (
                    f"🚨 **Developer Alert** {member.mention}\n"
                    f"**Issue:** {issue_type} detected by {component}\n"
                    f"**Count:** {total_issues} issues found\n"
                    f"**Action:** Check alerts and logs channels for details"
                )
            else:
                message = (
                    f"⚠️ **Issue Notification** {member.mention}\n"
                    f"**Issue:** {issue_type} detected by {component}\n"
                    f"**Count:** {total_issues} issues found\n"
                    f"**Action:** Check logs channel for details"
                )
                if dev_team_informed:
                    message += "\n*The dev team has been informed as well.*"

            await cmd_channel.send(message)

        except Exception as e:
            print(f"[NotificationManager] Failed to send individual cmd notification to {member.id}: {e}")
