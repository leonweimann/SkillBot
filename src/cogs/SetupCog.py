import discord
from discord import app_commands
from discord.ext import commands

from Utils.channels import get_channel_by_name
import Utils.environment as env
from Utils.errors import CodeError, UsageError
from Utils.database import DBUser
from Utils.logging import log
from Utils.members import get_student_nick, generate_student_channel_name
from Utils.msg import error_msg, success_msg, safe_respond
from Coordination.setup import setup_server as _setup_server


class SetupCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"[COG] {self.__cog_name__} is ready")

    @app_commands.command(
        name="setup-server",
        description="Initialisiert den Server für die Nutzung des Bots."
    )
    async def setup_server(self, interaction: discord.Interaction):
        if interaction.guild is None:
            raise UsageError("Dieser Befehl kann nur in einem Server verwendet werden.")

        if interaction.guild.owner_id is None:
            raise UsageError("Der Server hat keinen Besitzer.")

        if interaction.guild.owner_id != interaction.user.id:
            raise app_commands.MissingRole('Du musst der Server-Besitzer sein, um den Server zu als Nachhilfe Server zu initialisieren.')

        await interaction.response.defer()

        await _setup_server(interaction.guild)

        await interaction.followup.send(success_msg("Der Server wurde erfolgreich für die Nutzung des Bots konfiguriert."))

    @setup_server.error
    async def setup_server_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        match error:
            case app_commands.MissingRole():
                msg = error_msg("Du musst der Server-Besitzer sein, um den Server zu als Nachhilfe Server zu initialisieren.")
            case UsageError():
                msg = error_msg(str(error))
            case _:
                msg = error_msg("Ein unbekannter Fehler ist aufgetreten.", error)

        if interaction.guild and not isinstance(error, UsageError):
            await log(interaction.guild, msg)

        await safe_respond(interaction, msg, ephemeral=True)

    @app_commands.command(
        name='update-realname',
        description="Aktualisiert den echten Namen des Benutzers."
    )
    async def update_realname(self, interaction: discord.Interaction, user: discord.Member, new_realname: str):
        if interaction.guild is None:
            raise UsageError("Dieser Befehl kann nur in einem Server verwendet werden.")

        if interaction.user.id != user.id:
            if not isinstance(interaction.user, discord.Member):
                raise CodeError("Der Benutzer ist kein Mitglied des Servers.")

            admin_role = discord.utils.get(interaction.guild.roles, name='Admin')
            if admin_role is None:
                raise CodeError("Die Rolle 'Admin' existiert nicht.")
            teacher_role = env.get_teacher_role(interaction.guild)

            if admin_role not in interaction.user.roles and teacher_role not in interaction.user.roles:
                raise app_commands.MissingRole('Du musst Admin oder Lehrer sein, um den echten Namen eines anderen Benutzers zu aktualisieren.')

        # Update channel if student
        student_role = env.get_student_role(interaction.guild)
        if student_role in user.roles:
            # Update channel name
            old_name = user.nick
            if old_name is not None:
                student_channel = discord.utils.get(interaction.guild.text_channels, name=generate_student_channel_name(old_name))
                if student_channel is not None:
                    await student_channel.edit(name=generate_student_channel_name(new_realname))

        # Update realname
        await user.edit(nick=get_student_nick(new_realname))

        db_user = DBUser(user.id)
        db_user.edit(real_name=new_realname)

        await interaction.response.send_message(success_msg(f"Der echte Name von {user.mention} wurde erfolgreich zu '{new_realname}' aktualisiert."))


async def setup(bot):
    await bot.add_cog(SetupCog(bot))
