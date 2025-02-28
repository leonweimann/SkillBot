import discord
from discord import app_commands
from discord.ext import commands

import Utils.environment as env

from Utils.database import *
from Utils.errors import *
from Utils.logging import log


class MemberCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'[COG] {self.__cog_name__} is ready')

    # region Member Management

    @app_commands.command(
        name='rename-member',
        description="Setzt den echten Namen eines Nutzers auf einen neuen Wert."
    )
    async def rename_member(self, interaction: discord.Interaction, member: discord.Member, real_name: str):
        if not interaction.guild:
            raise CodeError("Dieser Befehl kann nur in einem Server verwendet werden")

        if not isinstance(interaction.user, discord.Member):
            raise CodeError("Dieser Befehl kann nur von Mitgliedern verwendet werden")

        db_member = User(interaction.guild.id, member.id)
        old_name = str(db_member.real_name)

        if interaction.user.id == member.id and env.is_admin(member):
            # Admin renames themselves

            db_member.edit(real_name=real_name)  # in db
            await member.edit(nick=env.generate_member_nick(db_member))  # in discord
            # Since only admins can rename themselves, no channel name change

        elif env.is_admin(interaction.user) and env.is_teacher(member):
            # Admin renames teacher

            category_channel = discord.utils.get(interaction.guild.categories, name=env.generate_member_nick(db_member))

            db_member.edit(real_name=real_name)  # in db
            await member.edit(nick=env.generate_member_nick(db_member))  # in discord

            if category_channel:
                await category_channel.edit(name=env.generate_member_nick(db_member))

        elif env.is_teacher(interaction.user) and env.is_student(member):
            # Teacher renames student

            ts_con = TeacherStudentConnection.find_by_student(interaction.guild.id, member.id)
            if not ts_con:
                raise UsageError("Du kannst nur Schüler umbenennen, die du unterrichtest")

            if ts_con.teacher_id != interaction.user.id:
                raise UsageError("Du kannst nur deine eigenen Schüler umbenennen")

            db_member.edit(real_name=real_name)  # in db
            await member.edit(nick=env.generate_member_nick(db_member))  # in discord

            if ts_con.channel_id:
                channel = interaction.guild.get_channel(ts_con.channel_id)
                if channel:
                    await channel.edit(name=env.generate_student_channel_name(real_name))
                else:
                    await log(interaction.guild, f"Channel für {member.mention} nicht gefunden, sollte aber `{ts_con.channel_id}` sein")
            else:
                await log(interaction.guild, f"Channel für {member.mention} nicht gefunden, da keine Verbindung existiert")

        else:
            raise UsageError("Du darfst diesen Nutzer nicht umbenennen")

        await env.send_safe_response(interaction, env.success_response(f"{member.mention} von `{old_name}` zu `{real_name}` umbenannt"))

    @rename_member.error
    async def rename_member_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        await env.handle_app_command_error(interaction, error, 'rename_member', 'Admin/Lehrer')

    # endregion


async def setup(bot):
    await bot.add_cog(MemberCog(bot))
