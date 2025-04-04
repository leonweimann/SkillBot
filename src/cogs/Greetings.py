import discord
from discord.ext import commands

from Utils.database import *
import Utils.environment as env
from Utils.logging import log


class Greetings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'[COG] {self.__cog_name__} is ready')

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        try:
            db_user = User(member.guild.id, member.id)

            if env.is_student(member):  # Delete student channel
                ts_con = TeacherStudentConnection.find_by_student(member.guild.id, member.id)
                if ts_con and ts_con.channel_id:
                    student_channel = member.guild.get_channel(ts_con.channel_id)
                    if student_channel:
                        await student_channel.delete()

            db_user.delete()

            await log(
                member.guild, f'Removed {member.mention if member.nick is None else member.nick} from database',
                details={
                    'Name': f'{member.name}',
                    'ID': f'{member.id}',
                    'Real Name': f'{db_user.real_name}',
                    'Hours in class': f'{db_user.hours_in_class}',
                    'User type': f'{'Student' if env.is_student(member) else 'Teacher' if env.is_teacher(member) else 'Unknown'}'
                }
            )
        except Exception as e:
            await log(
                member.guild, f'Failed to remove {member.mention if member.nick is None else member.nick} from database',
                details={
                    'Name': f'{member.name}',
                    'ID': f'{member.id}',
                    'Error': f'{e}'
                }
            )


async def setup(bot):
    await bot.add_cog(Greetings(bot))
