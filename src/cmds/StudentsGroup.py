import discord
from discord import app_commands
from typing import Callable

import Utils.environment as env
import Utils.database as db
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

    @staticmethod
    def _get_member(
        interaction: discord.Interaction,
        member_id: str
    ) -> discord.Member:
        if not interaction.guild:
            raise CodeError("Guild not found")
        return env.get_member(interaction.guild, member_id)

    # region Assignments

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
        member = self._get_member(interaction, member_id)

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
        return self._filter_members(
            interaction, current, lambda m: not env.is_assigned(m)
        )

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
        member = self._get_member(interaction, member_id)

        await student.unassign_student(
            interaction=interaction,
            student=member
        )

        await env.send_safe_response(
            interaction, env.success_response(f"Schüler {member.mention} abgemeldet")
        )

    @unassign.autocomplete('member_id')
    async def unassign_member_id_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return self._filter_members(
            interaction, current, env.is_student
        )

    @unassign.error
    async def unassign_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        await env.handle_app_command_error(
            interaction, error, command_name="students unassign", reqired_role="Lehrer"
        )

    # endregion Assignments

    # region Stashing

    @app_commands.command(
        name="stash",
        description="Stashes a student on this server."
    )
    @app_commands.describe(
        member_id="The member to stash"
    )
    @app_commands.checks.has_role('Lehrer')
    async def stash(self, interaction: discord.Interaction, member_id: str):
        member = self._get_member(interaction, member_id)

        await student.stash_student(
            interaction=interaction,
            student=member
        )

        await env.send_safe_response(
            interaction, env.success_response(f"Schüler {member.mention} archiviert")
        )

    @stash.autocomplete('member_id')
    async def stash_member_id_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return self._filter_members(
            interaction, current, lambda m: env.is_student(m) and not env.is_member_archived(m)
        )

    @stash.error
    async def stash_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        await env.handle_app_command_error(
            interaction, error, command_name="students stash", reqired_role="Lehrer"
        )

    @app_commands.command(
        name="pop",
        description="Unstashes a student on this server."
    )
    @app_commands.describe(
        member_id="The member to pop"
    )
    @app_commands.checks.has_role('Lehrer')
    async def pop(self, interaction: discord.Interaction, member_id: str):
        member = self._get_member(interaction, member_id)

        await student.pop_student(
            interaction=interaction,
            student=member
        )

        await env.send_safe_response(
            interaction, env.success_response(f"Schüler {member.mention} wiederhergestellt")
        )

    @pop.autocomplete('member_id')
    async def pop_member_id_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return self._filter_members(
            interaction, current, lambda m: env.is_student(m) and env.is_member_archived(m)
        )

    @pop.error
    async def pop_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        await env.handle_app_command_error(
            interaction, error, command_name="students pop", reqired_role="Lehrer"
        )

    # endregion Stashing

    # region Connections

    @app_commands.command(
        name='connect',
        description='Connects a member to an existing student.'
    )
    @app_commands.describe(
        member_id='The student to connect to',
        other_id='The member to connect to the student'
    )
    @app_commands.checks.has_role('Lehrer')
    async def connect(self, interaction: discord.Interaction, member_id: str, other_id: str):
        member = self._get_member(interaction, member_id)
        other = self._get_member(interaction, other_id)

        await student.connect_student(
            interaction=interaction,
            student=member,
            other_account=other
        )

        await env.send_safe_response(
            interaction, env.success_response(f"Schüler {other.mention} mit {member.mention} verbunden")
        )

    @connect.autocomplete('member_id')
    async def connect_member_id_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return self._filter_members(
            interaction, current, env.is_student
        )

    @connect.autocomplete('other_id')
    async def connect_other_id_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return self._filter_members(
            interaction, current, lambda m: not env.is_assigned(m)
        )

    @connect.error
    async def connect_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        await env.handle_app_command_error(
            interaction, error, command_name="students connect", reqired_role="Lehrer"
        )

    @app_commands.command(
        name='disconnect',
        description='Disconnects a member from an existing student.'
    )
    @app_commands.describe(
        member_id='The student to disconnect from',
        other_id='The member to disconnect from the student'
    )
    @app_commands.checks.has_role('Lehrer')
    async def disconnect(self, interaction: discord.Interaction, member_id: str, other_id: str):
        member = self._get_member(interaction, member_id)
        other = self._get_member(interaction, other_id)

        await student.disconnect_student(
            interaction=interaction,
            student=member,
            other_account=other
        )

        await env.send_safe_response(
            interaction, env.success_response(f"Schüler {other.mention} von {member.mention} getrennt")
        )

    @disconnect.autocomplete('member_id')
    async def disconnect_member_id_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return self._filter_members(
            interaction, current, env.is_student
        )

    @disconnect.autocomplete('other_id')
    async def disconnect_other_id_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return self._filter_members(
            interaction, current, env.is_student  # Could be done better, by filtering really only corresponding members / subusers
        )

    @disconnect.error
    async def disconnect_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        await env.handle_app_command_error(
            interaction, error, command_name="students disconnect", reqired_role="Lehrer"
        )

    # endregion Connections


async def setup(bot):
    bot.tree.add_command(
        StudentsGroup(
            name="students",
            description="Commands for students"
        )
    )
