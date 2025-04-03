import discord
from discord import app_commands

import Utils.environment as env
import Coordination.teacher as coord


@app_commands.guild_only()
class TeachersGroup(app_commands.Group):
    # region Assignments

    @app_commands.command(
        name="assign",
        description="Assigns a new teacher on this server."
    )
    @app_commands.describe(
        member_id="The member to assign",
        teacher_name="The name of the teacher"
    )
    @app_commands.checks.has_role('Admin')
    async def assign(self, interaction: discord.Interaction, member_id: str, teacher_name: str):
        teacher = env.get_member(interaction, member_id)

        await coord.assign_teacher(
            interaction=interaction,
            teacher=teacher,
            real_name=teacher_name,
            subjects=None,
            phonenumber=None,
            availability=None
        )

        await env.send_safe_response(
            interaction, env.success_response(f"Lehrer {teacher.mention} registriert")
        )

    @assign.autocomplete('member_id')
    async def assign_member_id_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return env.filter_members_for_autocomplete(
            interaction, current, lambda m: not env.is_assigned(m)
        )

    @assign.error
    async def assign_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        await env.handle_app_command_error(
            interaction, error, command_name="teachers assign", reqired_role="Admin"
        )

    @app_commands.command(
        name="unassign",
        description="Unassigns a teacher on this server."
    )
    @app_commands.describe(
        teacher_id="The teacher to unassign"
    )
    @app_commands.checks.has_role('Admin')
    async def unassign(self, interaction: discord.Interaction, teacher_id: str):
        teacher = env.get_member(interaction, teacher_id)

        await coord.unassign_teacher(
            interaction=interaction,
            teacher=teacher
        )

        await env.send_safe_response(
            interaction, env.success_response(f"Lehrer {teacher.mention} abgemeldet")
        )

    @unassign.autocomplete('teacher_id')
    async def unassign_teacher_id_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return env.filter_members_for_autocomplete(
            interaction, current, env.is_teacher
        )

    @unassign.error
    async def unassign_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        await env.handle_app_command_error(
            interaction, error, command_name="teachers unassign", reqired_role="Admin"
        )

    # endregion Assignments


async def setup(bot):
    bot.tree.add_command(
        TeachersGroup(
            name="teachers",
            description="Commands for teachers"
        )
    )
    print('[Group] TeachersGroup loaded')
