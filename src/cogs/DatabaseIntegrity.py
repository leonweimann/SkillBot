import discord
from discord.ext import commands, tasks
from typing import List, Dict, Any

from datetime import time, timezone, datetime

import Utils.environment as env
from Utils.database import DatabaseManager
from Utils.notifications import NotificationManager


class DatabaseIntegrity(commands.Cog):
    """
    Checks the data integrity of the database for each guild.

    This is a automated process running once a week.
    It ensures that the data in the database is consistent and valid.
    It checks for missing or corrupted data and logs any issues found.
    """

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'[COG] {self.__class__.__name__} is ready')
        # Start the weekly integrity check task
        if not self.weekly_integrity_check.is_running():
            self.weekly_integrity_check.start()

    @tasks.loop(time=time(hour=22, minute=0, tzinfo=timezone.utc))
    async def weekly_integrity_check(self):
        """
        Weekly database integrity check that runs every Saturday at 22:00 UTC (2:00 BER).

        This method is called automatically by the task loop.
        """
        current_time = datetime.now(timezone.utc)

        # Only run on Saturdays (weekday 5)
        if current_time.weekday() != 5:
            return

        print(f"[DatabaseIntegrity] Starting weekly integrity check at {current_time}")

        # Check each guild separately to provide guild-specific feedback
        for guild in self.bot.guilds:
            try:
                print(f"[DatabaseIntegrity] Checking integrity for guild {guild.id} ({guild.name})")
                await self._check_guild_integrity(guild)
            except Exception as e:
                error_msg = f"Error during integrity check for guild {guild.id} ({guild.name}): {e}"
                print(f"[DatabaseIntegrity] {error_msg}")

                # Send error notification to the specific guild
                try:
                    await NotificationManager.send_system_error(
                        guild=guild,
                        component="DatabaseIntegrity",
                        error_message="Weekly integrity check failed",
                        error_details=str(e),
                        context_user_id=None  # Weekly check has no specific user context
                    )
                except Exception as notification_error:
                    print(f"[DatabaseIntegrity] Failed to send error notification to guild {guild.id}: {notification_error}")

        print("[DatabaseIntegrity] Weekly integrity check completed for all guilds")

    @weekly_integrity_check.before_loop
    async def before_weekly_check(self):
        """Wait until the bot is ready before starting the task."""
        await self.bot.wait_until_ready()

    def cog_unload(self):
        """Clean up the task when the cog is unloaded."""
        self.weekly_integrity_check.cancel()

    # @commands.command(name="check_integrity", hidden=True)
    # @commands.has_permissions(administrator=True)
    # async def manual_integrity_check(self, ctx: commands.Context):
    #     """
    #     Manually trigger a database integrity check for the current guild.

    #     This command is restricted to administrators and is useful for testing
    #     or immediate checks when issues are suspected.
    #     """
    #     if ctx.guild is None:
    #         await ctx.send("❌ This command can only be used in a server.")
    #         return

    #     await ctx.send("🔍 Starting manual database integrity check...")

    #     try:
    #         await self._check_guild_integrity(ctx.guild)
    #         await ctx.send("✅ Manual integrity check completed. Check logs and alerts for details.")
    #     except Exception as e:
    #         await ctx.send(f"❌ Manual integrity check failed: {e}")
    #         print(f"[DatabaseIntegrity] Manual check failed for guild {ctx.guild.id}: {e}")

    async def _check_guild_integrity(self, guild: discord.Guild):
        """
        Check the database integrity for a specific guild.

        This method orchestrates all integrity checks for the guild.

        Args:
            guild: The Discord guild to check
        """
        print(f"[DatabaseIntegrity] Starting integrity checks for guild {guild.id} ({guild.name})")

        # List of all integrity check functions to run
        integrity_checks = [
            self._check_orphaned_subusers,
            # Add more integrity checks here as they are implemented:
            # self._check_orphaned_teachers,
            # self._check_invalid_user_data,
            # self._check_duplicate_records,
            # etc.
        ]

        all_issues_found = []
        total_checks_run = 0
        failed_checks = 0

        for check_func in integrity_checks:
            try:
                print(f"[DatabaseIntegrity] Running {check_func.__name__} for guild {guild.id}")
                issues = await check_func(guild)
                total_checks_run += 1

                if issues:
                    all_issues_found.extend(issues)
                    print(f"[DatabaseIntegrity] ⚠️  {check_func.__name__} found {len(issues)} issue(s)")
                else:
                    print(f"[DatabaseIntegrity] ✅ {check_func.__name__} passed")

            except Exception as e:
                failed_checks += 1
                error_msg = f"Failed to run {check_func.__name__}: {e}"
                print(f"[DatabaseIntegrity] ❌ {error_msg}")

                # Send error notification for this specific check
                await NotificationManager.send_system_error(
                    guild=guild,
                    component="DatabaseIntegrity",
                    error_message=f"Integrity check '{check_func.__name__}' failed",
                    error_details=error_msg,
                    context_user_id=None
                )

        # Send summary notification
        if all_issues_found:
            # Aggregate all issues by type
            issues_by_type = {}
            for issue in all_issues_found:
                issue_type = issue['type']
                if issue_type not in issues_by_type:
                    issues_by_type[issue_type] = []
                issues_by_type[issue_type].append(issue)

            # Create detailed report
            details_parts = [f"Guild: {guild.name} ({guild.id})", ""]
            total_issues = len(all_issues_found)

            for issue_type, issues in issues_by_type.items():
                details_parts.append(f"=== {issue_type} ({len(issues)} issues) ===")
                for issue in issues:
                    details_parts.append(f"- {issue['detail']}")
                details_parts.append("")

            details_text = "\n".join(details_parts)

            await NotificationManager.send_system_alert(
                guild=guild,
                issue_type="Database Integrity Issues",
                component="DatabaseIntegrity",
                total_issues=total_issues,
                details=details_text,
                context_user_id=None
            )

            print(f"[DatabaseIntegrity] ⚠️  Guild {guild.id} has {total_issues} total integrity issues across {len(issues_by_type)} categories")

        else:
            # All checks passed
            if failed_checks == 0:
                await NotificationManager.send_success_notification(
                    guild=guild,
                    component="DatabaseIntegrity",
                    message=f"All {total_checks_run} integrity checks completed successfully - no issues found"
                )
                print(f"[DatabaseIntegrity] ✅ All integrity checks passed for guild {guild.id} ({guild.name})")
            else:
                # Some checks failed but no issues were found in successful checks
                print(f"[DatabaseIntegrity] ⚠️  {failed_checks} integrity check(s) failed for guild {guild.id}, but {total_checks_run - failed_checks} successful checks found no issues")

    async def _check_orphaned_subusers(self, guild: discord.Guild) -> List[Dict[str, Any]]:
        """
        Check for subusers where the parent user doesn't exist.

        Args:
            guild: The Discord guild to check

        Returns:
            List of issue dictionaries, empty list if no issues found
        """
        issues: List[Dict[str, Any]] = []

        try:
            with DatabaseManager._connect(guild.id) as conn:
                cursor = conn.cursor()

                # Find subusers where the parent user doesn't exist
                cursor.execute('''
                    SELECT s.user_id, s.subuser_id
                    FROM subusers s
                    LEFT JOIN users u ON s.user_id = u.id
                    WHERE u.id IS NULL
                ''')

                orphaned_subusers = cursor.fetchall()

                for user_id, subuser_id in orphaned_subusers:
                    issue = {
                        'type': 'Orphaned Subusers',
                        'detail': f"user_id={user_id}, subuser_id={subuser_id} (parent user does not exist)",
                        'user_id': user_id,
                        'subuser_id': subuser_id
                    }
                    issues.append(issue)
                    print(f"[DatabaseIntegrity] ⚠️  ORPHANED SUBUSER: {issue['detail']}")

        except Exception as e:
            print(f"[DatabaseIntegrity] Error in _check_orphaned_subusers: {e}")
            raise

        return issues

    # Template for adding new integrity checks:
    # async def _check_new_integrity_issue(self, guild: discord.Guild) -> List[Dict[str, Any]]:
    #     """
    #     Check for [describe the integrity issue].
    #
    #     Args:
    #         guild: The Discord guild to check
    #
    #     Returns:
    #         List of issue dictionaries, empty list if no issues found
    #     """
    #     issues: List[Dict[str, Any]] = []
    #
    #     try:
    #         with DatabaseManager._connect(guild.id) as conn:
    #             cursor = conn.cursor()
    #
    #             # Your SQL query here
    #             cursor.execute('''
    #                 SELECT ...
    #                 FROM ...
    #                 WHERE ...
    #             ''')
    #
    #             problematic_records = cursor.fetchall()
    #
    #             for record in problematic_records:
    #                 issue = {
    #                     'type': 'Your Issue Type',
    #                     'detail': f"description of the specific issue: {record}",
    #                     # Add any relevant data fields
    #                 }
    #                 issues.append(issue)
    #                 print(f"[DatabaseIntegrity] ⚠️  YOUR ISSUE: {issue['detail']}")
    #
    #     except Exception as e:
    #         print(f"[DatabaseIntegrity] Error in _check_new_integrity_issue: {e}")
    #         raise
    #
    #     return issues


async def setup(bot):
    await bot.add_cog(DatabaseIntegrity(bot))
