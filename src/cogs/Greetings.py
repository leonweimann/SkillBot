import discord
from discord.ext import commands

import Utils.database as db
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
            db.add_user(member.id, member.name, member.discriminator, None, '👋', 'none')
            await log(
                member.guild, f'Added {member.mention if member.nick is None else member.nick} to database',
                details={
                    'Name': f'{member.name}#{member.discriminator}',
                    'ID': f'{member.id}'
                }
            )
        except Exception as e:
            raise e  # TODO: Handle this error

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        try:
            usr = db.get_user(member.id)

            db.remove_user(member.id)
            await log(
                member.guild, f'Removed {member.mention if member.nick is None else member.nick} from database',
                details={
                    'Name': f'{member.name}#{member.discriminator}',
                    'ID': f'{member.id}',
                    'Hours in class': f'{usr.hours_in_class}',
                    'User type': f'{usr.user_type}'
                }
            )
        except Exception as e:
            raise e  # TODO: Handle this error


async def setup(bot):
    await bot.add_cog(Greetings(bot))
