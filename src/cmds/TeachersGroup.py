import discord
from discord import app_commands

import Utils.environment as env
import Coordination.teacher as coord


@app_commands.guild_only()
class TeachersGroup(app_commands.Group):
    ...


async def setup(bot):
    bot.tree.add_command(
        TeachersGroup(
            name="teachers",
            description="Commands for teachers"
        )
    )
    print('[Group] TeachersGroup loaded')
