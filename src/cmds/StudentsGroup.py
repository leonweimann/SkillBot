import discord
from discord import app_commands
from typing import Callable

import Utils.environment as env


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
        member_name="The member to assign",
        real_name="The real name of the student",
        customer_id="The customer ID of the student"
    )
    @app_commands.checks.has_role('Lehrer')
    async def assign(self, interaction: discord.Interaction, member_name: str, real_name: str, customer_id: int):
        member = interaction.guild.get_member(int(member_name)) if interaction.guild else None
        if not member:
            await interaction.response.send_message("Member not found.", ephemeral=True)
            return

        await interaction.response.send_message(
            f"Assigning {member.display_name} as {real_name} with customer ID {customer_id}."
        )

    @assign.autocomplete('member_name')
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
        member_name="The member to unassign"
    )
    @app_commands.checks.has_role('Lehrer')
    async def unassign(self, interaction: discord.Interaction, member_name: str):
        member = interaction.guild.get_member(int(member_name)) if interaction.guild else None
        if not member:
            await interaction.response.send_message("Member not found.", ephemeral=True)
            return

        await interaction.response.send_message(
            f"Unassigning {member.display_name}."
        )

    @unassign.autocomplete('member_name')
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
