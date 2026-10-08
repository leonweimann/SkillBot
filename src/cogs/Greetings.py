import discord
from discord.ext import commands

from Utils.database import *
import Utils.environment as env  # noqa: F401 -- must be imported before Utils.lwlogging (circular import)
from Utils.lwlogging import log


def format_deleted_rows(deleted: dict[str, int]) -> str:
    """
    Formats the result of `DatabaseManager.purge_user` for a log entry.

    Args:
        deleted (dict[str, int]): Number of deleted rows per table.

    Returns:
        str: E.g. ``teacher_student=1, students=1, users=1`` (only tables with deleted rows), or ``none``.
    """
    return ', '.join(f'{table}={count}' for table, count in deleted.items() if count) or 'none'


class Greetings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'[COG] {self.__cog_name__} is ready')

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """
        Deletes the student channels and every database entry of a member who left the server.

        A teacher who still has students is kept (only a warning is logged), so the students' connections
        and channels stay intact until they are reassigned.
        """
        guild = member.guild
        name = member.display_name  # A mention of a departed member only renders as unknown user
        try:
            db_user = User(guild.id, member.id)
            user_type = 'Student' if db_user.is_student else 'Teacher' if db_user.is_teacher else 'Unknown'

            students = TeacherStudentConnection.find_all_by_teacher(guild.id, member.id)
            if students:
                await log(
                    guild, f'Kept {name} in database: teacher still has {len(students)} student(s)',
                    details={
                        'Name': f'{member.name}',
                        'ID': f'{member.id}',
                        'Real Name': f'{db_user.real_name}',
                        'Students': ', '.join(str(ts_con.student_id) for ts_con in students),
                    }
                )
                return

            # Delete the student channels (if they still exist) before their connections are purged
            channel_notes = []
            for ts_con in TeacherStudentConnection.find_all_by_student(guild.id, member.id):
                student_channel = guild.get_channel(ts_con.channel_id)
                if student_channel is None:
                    channel_notes.append(f'{ts_con.channel_id} not found')
                    continue
                try:
                    await student_channel.delete()
                    channel_notes.append(f'{ts_con.channel_id} deleted')
                except discord.HTTPException as e:  # The database is purged anyway
                    channel_notes.append(f'{ts_con.channel_id} not deleted: {e}')

            deleted = DatabaseManager.purge_user(guild.id, member.id)

            await log(
                guild, f'Removed {name} from database' if any(deleted.values()) else f'{name} left (no database entries)',
                details={
                    'Name': f'{member.name}',
                    'ID': f'{member.id}',
                    'Real Name': f'{db_user.real_name}',
                    'Hours in class': f'{db_user.hours_in_class}',
                    'User type': user_type,
                    'Channels': ', '.join(channel_notes) or 'none',
                    'Deleted rows': format_deleted_rows(deleted),
                }
            )
        except Exception as e:
            await log(
                guild, f'Failed to remove {name} from database',
                details={
                    'Name': f'{member.name}',
                    'ID': f'{member.id}',
                    'Error': f'{e}'
                }
            )


async def setup(bot):
    await bot.add_cog(Greetings(bot))
