import discord
from discord import app_commands
from typing import Callable

import Utils.environment as env
import Coordination.student as student

from Utils.errors import CodeError


class StudentsGroup(app_commands.Group):
    @staticmethod
    def _filter_members(
        interaction: discord.Interaction,
        current: str,
        predicate: Callable[[discord.Member], bool]
    ) -> list[app_commands.Choice[str]]:
        if not interaction.guild:
            return []

        filtered = (
            member for member in interaction.guild.members
            if predicate(member) and not member.bot and current.lower() in member.display_name.lower()
        )

        return [
            app_commands.Choice(name=member.display_name, value=str(member.id))
            for member in filtered
        ][:25]

    @app_commands.command(
        name="assign",
        description="Assigns a new student on this server."
    )
    @app_commands.describe(
        member_id="The member to assign",
        real_name="The real name of the student",
        customer_id="The customer ID of the student"
    )
    @app_commands.checks.has_role('Lehrer')
    async def assign(self, interaction: discord.Interaction, member_id: str, real_name: str, customer_id: int):
        if not interaction.guild:
            raise CodeError("Guild not found")

        member = env.get_member(interaction.guild, member_id)

        await student.assign_student(
            interaction=interaction,
            student=member,
            real_name=real_name,
            customer_id=customer_id,
            major=None,
            silent=False
        )

        await env.send_safe_response(
            interaction, env.success_response(f"Schüler {member.mention} registriert")
        )

    @assign.autocomplete('member_id')
    async def assign_member_id_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return self._filter_members(interaction, current, lambda m: not env.is_assigned(m))

    @assign.error
    async def assign_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        await env.handle_app_command_error(
            interaction, error, command_name="students assign", reqired_role="Lehrer"
        )

    @app_commands.command(
        name="unassign",
        description="Unassigns a student on this server."
    )
    @app_commands.describe(
        member_id="The member to unassign"
    )
    @app_commands.checks.has_role('Lehrer')
    async def unassign(self, interaction: discord.Interaction, member_id: str):
        if not interaction.guild:
            raise CodeError("Guild not found")

        member = env.get_member(interaction.guild, member_id)

        await student.unassign_student(
            interaction=interaction,
            student=member
        )

        await env.send_safe_response(
            interaction, env.success_response(f"Schüler {member.mention} abgemeldet")
        )

    @unassign.autocomplete('member_id')
    async def unassign_member_id_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return self._filter_members(interaction, current, env.is_student)

    @unassign.error
    async def unassign_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        await env.handle_app_command_error(
            interaction, error, command_name="students unassign", reqired_role="Lehrer"
        )


async def setup(bot):
    bot.tree.add_command(
        StudentsGroup(
            name="students",
            description="Commands for students"
        )
    )
