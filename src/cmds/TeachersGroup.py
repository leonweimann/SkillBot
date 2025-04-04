import discord
from discord import app_commands

import Utils.environment as env
import Coordination.teacher as coord


@app_commands.guild_only()
class TeachersGroup(app_commands.Group):
    # region Assignments

    @app_commands.command(
        name="assign",
        description="Weist einen neuen Lehrer auf diesem Server zu."
    )
    @app_commands.describe(
        member_id="Das Mitglied, das zugewiesen werden soll",
        teacher_name="Der Name des Lehrers"
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
        description="Meldet einen Lehrer auf diesem Server ab."
    )
    @app_commands.describe(
        teacher_id="Der Lehrer, der abgemeldet werden soll"
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

    # region Rename

    @app_commands.command(
        name='rename',
        description='Benennt einen Lehrer um'
    )
    @app_commands.describe(
        teacher_id='Der Lehrer, der umbenannt werden soll',
        new_name='Der neue Name des Lehrers'
    )
    @app_commands.checks.has_role('Admin')
    async def rename(self, interaction: discord.Interaction, teacher_id: str, new_name: str):
        teacher = env.get_member(interaction, teacher_id)

        await interaction.response.defer(thinking=True)
        old_name = await coord.rename_teacher(
            interaction=interaction,
            teacher=teacher,
            new_name=new_name
        )

        await interaction.followup.send(
            env.success_response(f"Lehrer {teacher.mention} umbenannt (ehemals `{old_name}`)")
        )

    @rename.autocomplete('teacher_id')
    async def rename_member_id_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return env.filter_members_for_autocomplete(
            interaction, current, env.is_teacher
        )

    @rename.error
    async def rename_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        await env.handle_app_command_error(
            interaction, error, command_name="teachers rename", reqired_role="Admin"
        )

    # endregion Rename


async def setup(bot):
    bot.tree.add_command(
        TeachersGroup(
            name="teachers",
            description="Befehle für Lehrer"
        )
    )
    print('[Group] TeachersGroup loaded')
