import discord
from discord.ext import commands

from Utils.database import *
from Utils.logging import log


class Greetings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'[COG] {self.__cog_name__} is ready')

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        try:
            db_user = DBUser(member.id)
            db_user.edit(real_name=member.name, icon='👋', user_type=None)

            await log(
                member.guild, f'Added {member.mention if member.nick is None else member.nick} to database',
                details={
                    'Name': f'{member.name}',
                    'ID': f'{member.id}'
                }
            )
        except Exception as e:
            await log(
                member.guild, f'Failed to add {member.mention if member.nick is None else member.nick} to database',
                details={
                    'Name': f'{member.name}',
                    'ID': f'{member.id}',
                    'Error': f'{e}'
                }
            )

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        try:
            db_user = DBUser(member.id)
            DatabaseManager.remove_user(member.id)

            await log(
                member.guild, f'Removed {member.mention if member.nick is None else member.nick} from database',
                details={
                    'Name': f'{member.name}',
                    'ID': f'{member.id}',
                    'Real Name': f'{db_user.real_name}',
                    'Hours in class': f'{db_user.hours_in_class}',
                    'User type': f'{db_user.user_type if db_user.user_type is not None else "None"}'
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
