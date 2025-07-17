import discord
from discord.ext import commands, tasks
from typing import List, Dict, Any, Optional
import asyncio

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

    # Configuration constants
    WEEKLY_CHECK_HOUR = 22  # 22:00 UTC (10 PM)
    WEEKLY_CHECK_MINUTE = 0
    WEEKLY_CHECK_DAY = 5    # Saturday (0=Monday, 6=Sunday)
    API_CALL_DELAY = 0.1    # Delay between Discord API calls to avoid rate limits
    MAX_CONCURRENT_API_CALLS = 5  # Maximum concurrent API calls

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

        # Only run on the configured day (Saturday by default)
        if current_time.weekday() != self.WEEKLY_CHECK_DAY:
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

    async def run_manual_integrity_check(self, guild: discord.Guild) -> Dict[str, Any]:
        """
        Run a manual database integrity check for a specific guild.

        This method can be called from commands to trigger an integrity check on demand.

        Args:
            guild: The Discord guild to check

        Returns:
            Dict containing check results with keys:
            - 'success': bool - Whether the check completed successfully
            - 'total_checks': int - Number of checks that were run
            - 'failed_checks': int - Number of checks that failed to run
            - 'total_issues': int - Total number of issues found
            - 'issues_by_type': dict - Issues grouped by type
            - 'duration': str - Time taken for the check
            - 'error_message': str - Error message if check failed completely
        """
        try:
            print(f"[DatabaseIntegrity] Manual integrity check started for guild {guild.id} ({guild.name})")
            result = await self._check_guild_integrity(guild, return_stats=True)
            if result:
                return {
                    'success': True,
                    'total_checks': result['total_checks'],
                    'failed_checks': result['failed_checks'],
                    'total_issues': result['total_issues'],
                    'issues_by_type': result['issues_by_type'],
                    'duration': result['duration'],
                    'message': 'Manual integrity check completed successfully'
                }
            else:
                return {
                    'success': False,
                    'error_message': 'Integrity check did not return results',
                    'total_checks': 0,
                    'failed_checks': 0,
                    'total_issues': 0,
                    'issues_by_type': {},
                    'duration': "0 seconds"
                }
        except Exception as e:
            error_msg = f"Manual integrity check failed for guild {guild.id}: {e}"
            print(f"[DatabaseIntegrity] {error_msg}")
            return {
                'success': False,
                'error_message': error_msg,
                'total_checks': 0,
                'failed_checks': 0,
                'total_issues': 0,
                'issues_by_type': {},
                'duration': "0 seconds"
            }

    async def _check_guild_integrity(self, guild: discord.Guild, return_stats: bool = False) -> Optional[Dict[str, Any]]:
        """
        Check the database integrity for a specific guild.

        This method orchestrates all integrity checks for the guild.

        Args:
            guild: The Discord guild to check
        """
        start_time = datetime.now(timezone.utc)
        print(f"[DatabaseIntegrity] Starting integrity checks for guild {guild.id} ({guild.name}) at {start_time}")

        # List of all integrity check functions to run
        integrity_checks = [
            self._check_orphaned_subusers,
            self._check_orphaned_teachers,
            self._check_orphaned_students,
            self._check_orphaned_teacher_student_connections,
            self._check_duplicate_users,
            self._check_invalid_user_data,
            self._check_voice_channel_joins_older_than_one_day,
            self._check_orphaned_dev_mode_entries,
            self._check_invalid_teacher_student_connections,
            self._check_duplicate_subuser_relationships,
            self._check_channel_id_duplicates,
            self._check_self_referencing_subusers,
            self._check_circular_subuser_references,
            self._check_nonexistent_discord_users,
            self._check_nonexistent_discord_channels
        ]

        all_issues_found = []
        total_checks_run = 0
        failed_checks = 0

        for check_func in integrity_checks:
            try:
                check_start_time = datetime.now(timezone.utc)
                print(f"[DatabaseIntegrity] Running {check_func.__name__} for guild {guild.id}")
                issues = await check_func(guild)
                check_duration = (datetime.now(timezone.utc) - check_start_time).total_seconds()
                total_checks_run += 1

                if issues:
                    all_issues_found.extend(issues)
                    print(f"[DatabaseIntegrity] ⚠️  {check_func.__name__} found {len(issues)} issue(s) in {check_duration:.2f}s")
                else:
                    print(f"[DatabaseIntegrity] ✅ {check_func.__name__} passed in {check_duration:.2f}s")

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

        # Calculate total duration
        end_time = datetime.now(timezone.utc)
        total_duration = (end_time - start_time).total_seconds()
        duration_str = f"{total_duration:.2f} seconds"
        if total_duration >= 60:
            duration_str = f"{total_duration / 60:.1f} minutes ({duration_str})"

        print(f"[DatabaseIntegrity] Completed integrity checks for guild {guild.id} in {duration_str}")

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
            details_parts = [
                f"Guild: {guild.name} ({guild.id})",
                f"Check Duration: {duration_str}",
                f"Checks Run: {total_checks_run}/{len(integrity_checks)}",
                ""
            ]
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
                    message=f"All {total_checks_run} integrity checks completed successfully in {duration_str} - no issues found"
                )
                print(f"[DatabaseIntegrity] ✅ All integrity checks passed for guild {guild.id} ({guild.name}) in {duration_str}")
            else:
                # Some checks failed but no issues were found in successful checks
                print(f"[DatabaseIntegrity] ⚠️  {failed_checks} integrity check(s) failed for guild {guild.id}, but {total_checks_run - failed_checks} successful checks found no issues (duration: {duration_str})")

        # Return statistics if requested (for manual checks)
        if return_stats:
            # Aggregate issues by type for stats
            issues_by_type = {}
            for issue in all_issues_found:
                issue_type = issue['type']
                if issue_type not in issues_by_type:
                    issues_by_type[issue_type] = []
                issues_by_type[issue_type].append(issue)

            return {
                'total_checks': total_checks_run,
                'failed_checks': failed_checks,
                'total_issues': len(all_issues_found),
                'issues_by_type': issues_by_type,
                'duration': duration_str
            }

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

    async def _check_orphaned_teachers(self, guild: discord.Guild) -> List[Dict[str, Any]]:
        """
        Check for teachers where the parent user doesn't exist.

        Args:
            guild: The Discord guild to check

        Returns:
            List of issue dictionaries, empty list if no issues found
        """
        issues: List[Dict[str, Any]] = []

        try:
            with DatabaseManager._connect(guild.id) as conn:
                cursor = conn.cursor()

                # Find teachers where the parent user doesn't exist
                cursor.execute('''
                    SELECT t.user_id
                    FROM teachers t
                    LEFT JOIN users u ON t.user_id = u.id
                    WHERE u.id IS NULL
                ''')

                orphaned_teachers = cursor.fetchall()

                for (user_id,) in orphaned_teachers:
                    issue = {
                        'type': 'Orphaned Teachers',
                        'detail': f"teacher user_id={user_id} (parent user does not exist)",
                        'user_id': user_id
                    }
                    issues.append(issue)
                    print(f"[DatabaseIntegrity] ⚠️  ORPHANED TEACHER: {issue['detail']}")

        except Exception as e:
            print(f"[DatabaseIntegrity] Error in _check_orphaned_teachers: {e}")
            raise

        return issues

    async def _check_orphaned_students(self, guild: discord.Guild) -> List[Dict[str, Any]]:
        """
        Check for students where the parent user doesn't exist.

        Args:
            guild: The Discord guild to check

        Returns:
            List of issue dictionaries, empty list if no issues found
        """
        issues: List[Dict[str, Any]] = []

        try:
            with DatabaseManager._connect(guild.id) as conn:
                cursor = conn.cursor()

                # Find students where the parent user doesn't exist
                cursor.execute('''
                    SELECT s.user_id
                    FROM students s
                    LEFT JOIN users u ON s.user_id = u.id
                    WHERE u.id IS NULL
                ''')

                orphaned_students = cursor.fetchall()

                for (user_id,) in orphaned_students:
                    issue = {
                        'type': 'Orphaned Students',
                        'detail': f"student user_id={user_id} (parent user does not exist)",
                        'user_id': user_id
                    }
                    issues.append(issue)
                    print(f"[DatabaseIntegrity] ⚠️  ORPHANED STUDENT: {issue['detail']}")

        except Exception as e:
            print(f"[DatabaseIntegrity] Error in _check_orphaned_students: {e}")
            raise

        return issues

    async def _check_orphaned_teacher_student_connections(self, guild: discord.Guild) -> List[Dict[str, Any]]:
        """
        Check for teacher-student connections where either the teacher or student doesn't exist.

        Args:
            guild: The Discord guild to check

        Returns:
            List of issue dictionaries, empty list if no issues found
        """
        issues: List[Dict[str, Any]] = []

        try:
            with DatabaseManager._connect(guild.id) as conn:
                cursor = conn.cursor()

                # Find connections where the teacher doesn't exist
                cursor.execute('''
                    SELECT ts.teacher_id, ts.student_id, ts.channel_id
                    FROM teacher_student ts
                    LEFT JOIN teachers t ON ts.teacher_id = t.user_id
                    WHERE t.user_id IS NULL
                ''')

                orphaned_by_teacher = cursor.fetchall()

                for teacher_id, student_id, channel_id in orphaned_by_teacher:
                    issue = {
                        'type': 'Orphaned Teacher-Student Connections',
                        'detail': f"connection teacher_id={teacher_id}, student_id={student_id}, channel_id={channel_id} (teacher does not exist)",
                        'teacher_id': teacher_id,
                        'student_id': student_id,
                        'channel_id': channel_id
                    }
                    issues.append(issue)
                    print(f"[DatabaseIntegrity] ⚠️  ORPHANED CONNECTION (missing teacher): {issue['detail']}")

                # Find connections where the student doesn't exist
                cursor.execute('''
                    SELECT ts.teacher_id, ts.student_id, ts.channel_id
                    FROM teacher_student ts
                    LEFT JOIN students s ON ts.student_id = s.user_id
                    WHERE s.user_id IS NULL
                ''')

                orphaned_by_student = cursor.fetchall()

                for teacher_id, student_id, channel_id in orphaned_by_student:
                    issue = {
                        'type': 'Orphaned Teacher-Student Connections',
                        'detail': f"connection teacher_id={teacher_id}, student_id={student_id}, channel_id={channel_id} (student does not exist)",
                        'teacher_id': teacher_id,
                        'student_id': student_id,
                        'channel_id': channel_id
                    }
                    issues.append(issue)
                    print(f"[DatabaseIntegrity] ⚠️  ORPHANED CONNECTION (missing student): {issue['detail']}")

        except Exception as e:
            print(f"[DatabaseIntegrity] Error in _check_orphaned_teacher_student_connections: {e}")
            raise

        return issues

    async def _check_duplicate_users(self, guild: discord.Guild) -> List[Dict[str, Any]]:
        """
        Check for duplicate user entries (this shouldn't happen due to PRIMARY KEY constraint).

        Args:
            guild: The Discord guild to check

        Returns:
            List of issue dictionaries, empty list if no issues found
        """
        issues: List[Dict[str, Any]] = []

        try:
            with DatabaseManager._connect(guild.id) as conn:
                cursor = conn.cursor()

                # Check for duplicate user IDs (should be impossible due to PRIMARY KEY)
                cursor.execute('''
                    SELECT id, COUNT(*)
                    FROM users
                    GROUP BY id
                    HAVING COUNT(*) > 1
                ''')

                duplicate_users = cursor.fetchall()

                for user_id, count in duplicate_users:
                    issue = {
                        'type': 'Duplicate Users',
                        'detail': f"user_id={user_id} appears {count} times in users table",
                        'user_id': user_id,
                        'count': count
                    }
                    issues.append(issue)
                    print(f"[DatabaseIntegrity] ⚠️  DUPLICATE USER: {issue['detail']}")

        except Exception as e:
            print(f"[DatabaseIntegrity] Error in _check_duplicate_users: {e}")
            raise

        return issues

    async def _check_invalid_user_data(self, guild: discord.Guild) -> List[Dict[str, Any]]:
        """
        Check for invalid user data (negative hours, invalid IDs, etc.).

        Args:
            guild: The Discord guild to check

        Returns:
            List of issue dictionaries, empty list if no issues found
        """
        issues: List[Dict[str, Any]] = []

        try:
            with DatabaseManager._connect(guild.id) as conn:
                cursor = conn.cursor()

                # Check for negative hours_in_class
                cursor.execute('''
                    SELECT id, hours_in_class
                    FROM users
                    WHERE hours_in_class < 0
                ''')

                negative_hours = cursor.fetchall()

                for user_id, hours in negative_hours:
                    issue = {
                        'type': 'Invalid User Data',
                        'detail': f"user_id={user_id} has negative hours_in_class: {hours}",
                        'user_id': user_id,
                        'hours_in_class': hours
                    }
                    issues.append(issue)
                    print(f"[DatabaseIntegrity] ⚠️  INVALID USER DATA: {issue['detail']}")

                # Check for invalid user IDs (should be positive Discord snowflakes)
                cursor.execute('''
                    SELECT id
                    FROM users
                    WHERE id <= 0
                ''')

                invalid_ids = cursor.fetchall()

                for (user_id,) in invalid_ids:
                    issue = {
                        'type': 'Invalid User Data',
                        'detail': f"user_id={user_id} is not a valid Discord ID (must be positive)",
                        'user_id': user_id
                    }
                    issues.append(issue)
                    print(f"[DatabaseIntegrity] ⚠️  INVALID USER ID: {issue['detail']}")

        except Exception as e:
            print(f"[DatabaseIntegrity] Error in _check_invalid_user_data: {e}")
            raise

        return issues

    async def _check_voice_channel_joins_older_than_one_day(self, guild: discord.Guild) -> List[Dict[str, Any]]:
        """
        Check for voice channel joins that are older than one day, which shouldn't happen.

        Args:
            guild: The Discord guild to check

        Returns:
            List of issue dictionaries, empty list if no issues found
        """
        issues: List[Dict[str, Any]] = []

        try:
            with DatabaseManager._connect(guild.id) as conn:
                cursor = conn.cursor()

                # Check for voice channel joins older than 24 hours
                cursor.execute('''
                    SELECT user_id, voice_channel_id, join_time
                    FROM user_voice_channel_join
                    WHERE datetime(join_time) < datetime('now', '-1 day')
                ''')

                old_joins = cursor.fetchall()

                for user_id, voice_channel_id, join_time in old_joins:
                    issue = {
                        'type': 'Stale Voice Channel Joins',
                        'detail': f"user_id={user_id} has voice channel join older than 1 day: {join_time} (channel_id={voice_channel_id})",
                        'user_id': user_id,
                        'voice_channel_id': voice_channel_id,
                        'join_time': join_time
                    }
                    issues.append(issue)
                    print(f"[DatabaseIntegrity] ⚠️  STALE VOICE JOIN: {issue['detail']}")

        except Exception as e:
            print(f"[DatabaseIntegrity] Error in _check_voice_channel_joins_older_than_one_day: {e}")
            raise

        return issues

    async def _check_orphaned_dev_mode_entries(self, guild: discord.Guild) -> List[Dict[str, Any]]:
        """
        Check for dev_mode entries where the parent user doesn't exist.

        Args:
            guild: The Discord guild to check

        Returns:
            List of issue dictionaries, empty list if no issues found
        """
        issues: List[Dict[str, Any]] = []

        try:
            with DatabaseManager._connect(guild.id) as conn:
                cursor = conn.cursor()

                # Find dev_mode entries where the parent user doesn't exist
                cursor.execute('''
                    SELECT d.user_id, d.is_active
                    FROM dev_mode d
                    LEFT JOIN users u ON d.user_id = u.id
                    WHERE u.id IS NULL
                ''')

                orphaned_dev_mode = cursor.fetchall()

                for user_id, is_active in orphaned_dev_mode:
                    issue = {
                        'type': 'Orphaned Dev Mode Entries',
                        'detail': f"dev_mode user_id={user_id}, is_active={is_active} (parent user does not exist)",
                        'user_id': user_id,
                        'is_active': is_active
                    }
                    issues.append(issue)
                    print(f"[DatabaseIntegrity] ⚠️  ORPHANED DEV MODE: {issue['detail']}")

        except Exception as e:
            print(f"[DatabaseIntegrity] Error in _check_orphaned_dev_mode_entries: {e}")
            raise

        return issues

    async def _check_invalid_teacher_student_connections(self, guild: discord.Guild) -> List[Dict[str, Any]]:
        """
        Check for invalid teacher-student connections (same person as teacher and student, invalid channel IDs).

        Args:
            guild: The Discord guild to check

        Returns:
            List of issue dictionaries, empty list if no issues found
        """
        issues: List[Dict[str, Any]] = []

        try:
            with DatabaseManager._connect(guild.id) as conn:
                cursor = conn.cursor()

                # Check for connections where teacher and student are the same person
                cursor.execute('''
                    SELECT teacher_id, student_id, channel_id
                    FROM teacher_student
                    WHERE teacher_id = student_id
                ''')

                self_connections = cursor.fetchall()

                for teacher_id, student_id, channel_id in self_connections:
                    issue = {
                        'type': 'Invalid Teacher-Student Connections',
                        'detail': f"teacher_id={teacher_id} and student_id={student_id} are the same person (channel_id={channel_id})",
                        'teacher_id': teacher_id,
                        'student_id': student_id,
                        'channel_id': channel_id
                    }
                    issues.append(issue)
                    print(f"[DatabaseIntegrity] ⚠️  SELF-CONNECTION: {issue['detail']}")

                # Check for invalid channel IDs (should be positive)
                cursor.execute('''
                    SELECT teacher_id, student_id, channel_id
                    FROM teacher_student
                    WHERE channel_id <= 0
                ''')

                invalid_channels = cursor.fetchall()

                for teacher_id, student_id, channel_id in invalid_channels:
                    issue = {
                        'type': 'Invalid Teacher-Student Connections',
                        'detail': f"connection teacher_id={teacher_id}, student_id={student_id} has invalid channel_id={channel_id}",
                        'teacher_id': teacher_id,
                        'student_id': student_id,
                        'channel_id': channel_id
                    }
                    issues.append(issue)
                    print(f"[DatabaseIntegrity] ⚠️  INVALID CHANNEL ID: {issue['detail']}")

        except Exception as e:
            print(f"[DatabaseIntegrity] Error in _check_invalid_teacher_student_connections: {e}")
            raise

        return issues

    async def _check_duplicate_subuser_relationships(self, guild: discord.Guild) -> List[Dict[str, Any]]:
        """
        Check for duplicate subuser relationships.

        Args:
            guild: The Discord guild to check

        Returns:
            List of issue dictionaries, empty list if no issues found
        """
        issues: List[Dict[str, Any]] = []

        try:
            with DatabaseManager._connect(guild.id) as conn:
                cursor = conn.cursor()

                # Check for duplicate subuser relationships
                cursor.execute('''
                    SELECT user_id, subuser_id, COUNT(*)
                    FROM subusers
                    GROUP BY user_id, subuser_id
                    HAVING COUNT(*) > 1
                ''')

                duplicate_subusers = cursor.fetchall()

                for user_id, subuser_id, count in duplicate_subusers:
                    issue = {
                        'type': 'Duplicate Subuser Relationships',
                        'detail': f"subuser relationship user_id={user_id}, subuser_id={subuser_id} appears {count} times",
                        'user_id': user_id,
                        'subuser_id': subuser_id,
                        'count': count
                    }
                    issues.append(issue)
                    print(f"[DatabaseIntegrity] ⚠️  DUPLICATE SUBUSER: {issue['detail']}")

        except Exception as e:
            print(f"[DatabaseIntegrity] Error in _check_duplicate_subuser_relationships: {e}")
            raise

        return issues

    async def _check_channel_id_duplicates(self, guild: discord.Guild) -> List[Dict[str, Any]]:
        """
        Check for duplicate channel IDs in teacher_student connections (should be unique).

        Args:
            guild: The Discord guild to check

        Returns:
            List of issue dictionaries, empty list if no issues found
        """
        issues: List[Dict[str, Any]] = []

        try:
            with DatabaseManager._connect(guild.id) as conn:
                cursor = conn.cursor()

                # Check for duplicate channel IDs in teacher_student table
                cursor.execute('''
                    SELECT channel_id, COUNT(*)
                    FROM teacher_student
                    GROUP BY channel_id
                    HAVING COUNT(*) > 1
                ''')

                duplicate_channels = cursor.fetchall()

                for channel_id, count in duplicate_channels:
                    issue = {
                        'type': 'Duplicate Channel IDs',
                        'detail': f"channel_id={channel_id} is used by {count} different teacher-student connections",
                        'channel_id': channel_id,
                        'count': count
                    }
                    issues.append(issue)
                    print(f"[DatabaseIntegrity] ⚠️  DUPLICATE CHANNEL ID: {issue['detail']}")

                    # Get the specific connections using this channel
                    cursor.execute('''
                        SELECT teacher_id, student_id
                        FROM teacher_student
                        WHERE channel_id = ?
                    ''', (channel_id,))

                    connections = cursor.fetchall()
                    for teacher_id, student_id in connections:
                        print(f"[DatabaseIntegrity]   └─ Used by teacher_id={teacher_id}, student_id={student_id}")

        except Exception as e:
            print(f"[DatabaseIntegrity] Error in _check_channel_id_duplicates: {e}")
            raise

        return issues

    async def _check_self_referencing_subusers(self, guild: discord.Guild) -> List[Dict[str, Any]]:
        """
        Check for subuser relationships where user_id equals subuser_id (self-referencing).

        Args:
            guild: The Discord guild to check

        Returns:
            List of issue dictionaries, empty list if no issues found
        """
        issues: List[Dict[str, Any]] = []

        try:
            with DatabaseManager._connect(guild.id) as conn:
                cursor = conn.cursor()

                # Check for self-referencing subuser relationships
                cursor.execute('''
                    SELECT user_id, subuser_id
                    FROM subusers
                    WHERE user_id = subuser_id
                ''')

                self_referencing = cursor.fetchall()

                for user_id, subuser_id in self_referencing:
                    issue = {
                        'type': 'Self-Referencing Subusers',
                        'detail': f"user_id={user_id} references itself as a subuser (subuser_id={subuser_id})",
                        'user_id': user_id,
                        'subuser_id': subuser_id
                    }
                    issues.append(issue)
                    print(f"[DatabaseIntegrity] ⚠️  SELF-REFERENCING SUBUSER: {issue['detail']}")

        except Exception as e:
            print(f"[DatabaseIntegrity] Error in _check_self_referencing_subusers: {e}")
            raise

        return issues

    async def _check_circular_subuser_references(self, guild: discord.Guild) -> List[Dict[str, Any]]:
        """
        Check for circular subuser references (A -> B -> A).

        Args:
            guild: The Discord guild to check

        Returns:
            List of issue dictionaries, empty list if no issues found
        """
        issues: List[Dict[str, Any]] = []

        try:
            with DatabaseManager._connect(guild.id) as conn:
                cursor = conn.cursor()

                # Get all subuser relationships
                cursor.execute('''
                    SELECT user_id, subuser_id
                    FROM subusers
                ''')

                relationships = cursor.fetchall()

                # Build a graph to detect cycles
                graph = {}
                for user_id, subuser_id in relationships:
                    if user_id not in graph:
                        graph[user_id] = []
                    graph[user_id].append(subuser_id)

                # Use DFS to detect cycles
                visited = set()
                recursion_stack = set()

                def has_cycle(node, path):
                    if node in recursion_stack:
                        # Found a cycle - find the cycle part
                        cycle_start = path.index(node)
                        cycle = path[cycle_start:] + [node]
                        return cycle
                    if node in visited:
                        return None

                    visited.add(node)
                    recursion_stack.add(node)

                    if node in graph:
                        for neighbor in graph[node]:
                            cycle = has_cycle(neighbor, path + [node])
                            if cycle:
                                return cycle

                    recursion_stack.remove(node)
                    return None

                # Check each node for cycles
                for start_node in graph:
                    if start_node not in visited:
                        cycle = has_cycle(start_node, [])
                        if cycle:
                            issue = {
                                'type': 'Circular Subuser References',
                                'detail': f"circular reference detected: {' -> '.join(map(str, cycle))}",
                                'cycle': cycle
                            }
                            issues.append(issue)
                            print(f"[DatabaseIntegrity] ⚠️  CIRCULAR SUBUSER REFERENCE: {issue['detail']}")

        except Exception as e:
            print(f"[DatabaseIntegrity] Error in _check_circular_subuser_references: {e}")
            raise

        return issues

    async def _check_nonexistent_discord_users(self, guild: discord.Guild) -> List[Dict[str, Any]]:
        """
        Check for user IDs in the database that don't exist as Discord users in the guild.

        Args:
            guild: The Discord guild to check

        Returns:
            List of issue dictionaries, empty list if no issues found
        """
        issues: List[Dict[str, Any]] = []

        try:
            with DatabaseManager._connect(guild.id) as conn:
                cursor = conn.cursor()

                # Get all unique user IDs from all tables
                user_ids = set()

                # From users table
                cursor.execute('SELECT id FROM users')
                user_ids.update(row[0] for row in cursor.fetchall())

                # From subusers table (both user_id and subuser_id)
                cursor.execute('SELECT DISTINCT user_id FROM subusers UNION SELECT DISTINCT subuser_id FROM subusers')
                user_ids.update(row[0] for row in cursor.fetchall())

                # From user_voice_channel_join table
                cursor.execute('SELECT DISTINCT user_id FROM user_voice_channel_join')
                user_ids.update(row[0] for row in cursor.fetchall())

                # From dev_mode table
                cursor.execute('SELECT DISTINCT user_id FROM dev_mode')
                user_ids.update(row[0] for row in cursor.fetchall())

                # Check each user ID against Discord guild members
                api_calls_made = 0
                for user_id in user_ids:
                    try:
                        # Try to get the member from the guild
                        member = guild.get_member(user_id)
                        if member is None:
                            # Try to fetch the member (in case they're not cached)
                            try:
                                member = await guild.fetch_member(user_id)
                                api_calls_made += 1
                                # Rate limiting: pause between API calls
                                if api_calls_made % self.MAX_CONCURRENT_API_CALLS == 0:
                                    await asyncio.sleep(self.API_CALL_DELAY)
                            except discord.NotFound:
                                issue = {
                                    'type': 'Nonexistent Discord Users',
                                    'detail': f"user_id={user_id} exists in database but is not a member of guild {guild.name} ({guild.id})",
                                    'user_id': user_id
                                }
                                issues.append(issue)
                                print(f"[DatabaseIntegrity] ⚠️  NONEXISTENT DISCORD USER: {issue['detail']}")
                            except discord.HTTPException as e:
                                # Other HTTP errors (rate limits, etc.) - skip this check
                                print(f"[DatabaseIntegrity] Warning: Could not fetch user {user_id}: {e}")
                    except Exception as e:
                        print(f"[DatabaseIntegrity] Warning: Error checking user {user_id}: {e}")

        except Exception as e:
            print(f"[DatabaseIntegrity] Error in _check_nonexistent_discord_users: {e}")
            raise

        return issues

    async def _check_nonexistent_discord_channels(self, guild: discord.Guild) -> List[Dict[str, Any]]:
        """
        Check for channel IDs in the database that don't exist as Discord channels in the guild.

        Args:
            guild: The Discord guild to check

        Returns:
            List of issue dictionaries, empty list if no issues found
        """
        issues: List[Dict[str, Any]] = []

        try:
            with DatabaseManager._connect(guild.id) as conn:
                cursor = conn.cursor()

                # Get all channel IDs from teacher_student table
                cursor.execute('SELECT DISTINCT channel_id FROM teacher_student')
                channel_ids = [row[0] for row in cursor.fetchall()]

                # Get all voice channel IDs from user_voice_channel_join table
                cursor.execute('SELECT DISTINCT voice_channel_id FROM user_voice_channel_join')
                voice_channel_ids = [row[0] for row in cursor.fetchall()]

                # Combine all channel IDs
                all_channel_ids = set(channel_ids + voice_channel_ids)

                # Check each channel ID against Discord guild channels
                api_calls_made = 0
                for channel_id in all_channel_ids:
                    try:
                        # Try to get the channel from the guild
                        channel = guild.get_channel(channel_id)
                        if channel is None:
                            # Try to fetch the channel (in case it's not cached)
                            try:
                                channel = await self.bot.fetch_channel(channel_id)
                                api_calls_made += 1
                                # Rate limiting: pause between API calls
                                if api_calls_made % self.MAX_CONCURRENT_API_CALLS == 0:
                                    await asyncio.sleep(self.API_CALL_DELAY)
                                # Verify the channel belongs to this guild
                                if not hasattr(channel, 'guild') or channel.guild.id != guild.id:
                                    channel = None
                            except discord.NotFound:
                                channel = None
                            except discord.HTTPException as e:
                                # Other HTTP errors (rate limits, etc.) - skip this check
                                print(f"[DatabaseIntegrity] Warning: Could not fetch channel {channel_id}: {e}")
                                continue

                            if channel is None:
                                # Determine which table(s) reference this channel
                                tables_referencing = []
                                if channel_id in channel_ids:
                                    tables_referencing.append("teacher_student")
                                if channel_id in voice_channel_ids:
                                    tables_referencing.append("user_voice_channel_join")

                                issue = {
                                    'type': 'Nonexistent Discord Channels',
                                    'detail': f"channel_id={channel_id} exists in database ({', '.join(tables_referencing)}) but does not exist in guild {guild.name} ({guild.id})",
                                    'channel_id': channel_id,
                                    'tables': tables_referencing
                                }
                                issues.append(issue)
                                print(f"[DatabaseIntegrity] ⚠️  NONEXISTENT DISCORD CHANNEL: {issue['detail']}")
                    except Exception as e:
                        print(f"[DatabaseIntegrity] Warning: Error checking channel {channel_id}: {e}")

        except Exception as e:
            print(f"[DatabaseIntegrity] Error in _check_nonexistent_discord_channels: {e}")
            raise

        return issues


async def setup(bot):
    await bot.add_cog(DatabaseIntegrity(bot))
