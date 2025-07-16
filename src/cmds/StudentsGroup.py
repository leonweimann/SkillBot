import discord
from discord import app_commands

import Utils.environment as env
import Coordination.student as coord


@app_commands.guild_only()
class StudentsGroup(app_commands.Group):
    # region Assignments

    @app_commands.command(
        name="assign",
        description="Weist einen neuen Schüler diesem Server zu."
    )
    @app_commands.describe(
        member_id="Das Mitglied, das zugewiesen werden soll",
        real_name="Der richtige Name des Schülers",
        customer_id="Die Kunden-ID des Schülers"
    )
    @app_commands.checks.has_role('Lehrer')
    async def assign(self, interaction: discord.Interaction, member_id: str, real_name: str, customer_id: int):
        member = env.get_member(interaction, member_id)

        await interaction.response.defer(thinking=True)
        await coord.assign_student(
            interaction=interaction,
            student=member,
            real_name=real_name,
            customer_id=customer_id,
            silent=False
        )

        await interaction.followup.send(
            env.success_response(f"Schüler {member.mention} registriert")
        )

    @assign.autocomplete('member_id')
    async def assign_member_id_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return env.filter_members_for_autocomplete(
            interaction, current, lambda m: not env.is_assigned(m)
        )

    @assign.error
    async def assign_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        await env.handle_app_command_error(
            interaction, error, command_name="students assign", reqired_role="Lehrer"
        )

    @app_commands.command(
        name="unassign",
        description="Meldet einen Schüler von diesem Server ab."
    )
    @app_commands.describe(
        student_id="Der Schüler, der abgemeldet werden soll"
    )
    @app_commands.checks.has_role('Lehrer')
    async def unassign(self, interaction: discord.Interaction, student_id: str):
        student = env.get_member(interaction, student_id)

        await interaction.response.defer(thinking=True)
        await coord.unassign_student(
            interaction=interaction,
            student=student
        )

        await interaction.followup.send(
            env.success_response(f"Schüler {student.mention} abgemeldet")
        )

    @unassign.autocomplete('student_id')
    async def unassign_member_id_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return env.filter_members_for_autocomplete(
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
        description="Archiviert einen Schüler auf diesem Server."
    )
    @app_commands.describe(
        student_id="Der Schüler, der archiviert werden soll"
    )
    @app_commands.checks.has_role('Lehrer')
    async def stash(self, interaction: discord.Interaction, student_id: str):
        student = env.get_member(interaction, student_id)

        await interaction.response.defer(thinking=True)
        await coord.stash_student(
            interaction=interaction,
            student=student
        )

        await interaction.followup.send(
            env.success_response(f"Schüler {student.mention} archiviert")
        )

    @stash.autocomplete('student_id')
    async def stash_member_id_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return env.filter_members_for_autocomplete(
            interaction, current, lambda m: env.is_student(m) and not env.is_member_archived(m)  # Doesn't work as expected
        )

    @stash.error
    async def stash_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        await env.handle_app_command_error(
            interaction, error, command_name="students stash", reqired_role="Lehrer"
        )

    @app_commands.command(
        name="pop",
        description="Stellt einen archivierten Schüler wieder her."
    )
    @app_commands.describe(
        student_id="Der Schüler, der wiederhergestellt werden soll"
    )
    @app_commands.checks.has_role('Lehrer')
    async def pop(self, interaction: discord.Interaction, student_id: str):
        student = env.get_member(interaction, student_id)

        await interaction.response.defer(thinking=True)
        await coord.pop_student(
            interaction=interaction,
            student=student
        )

        await interaction.followup.send(
            env.success_response(f"Schüler {student.mention} wiederhergestellt")
        )

    @pop.autocomplete('student_id')
    async def pop_member_id_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return env.filter_members_for_autocomplete(
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
        description='Verbindet ein Mitglied mit einem bestehenden Schüler.'
    )
    @app_commands.describe(
        student_id='Der Schüler, mit dem verbunden werden soll',
        new_account_id='Das Mitglied, das mit dem Schüler verbunden werden soll'
    )
    @app_commands.checks.has_role('Lehrer')
    async def connect(self, interaction: discord.Interaction, student_id: str, new_account_id: str):
        student = env.get_member(interaction, student_id)
        new_account = env.get_member(interaction, new_account_id)

        await interaction.response.defer(thinking=True)
        await coord.connect_student(
            interaction=interaction,
            student=student,
            other_account=new_account
        )

        await interaction.followup.send(
            env.success_response(f"Schüler {new_account.mention} mit {student.mention} verbunden")
        )

    @connect.autocomplete('student_id')
    async def connect_member_id_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return env.filter_members_for_autocomplete(
            interaction, current, env.is_student
        )

    @connect.autocomplete('new_account_id')
    async def connect_other_id_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return env.filter_members_for_autocomplete(
            interaction, current, lambda m: not env.is_assigned(m)
        )

    @connect.error
    async def connect_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        await env.handle_app_command_error(
            interaction, error, command_name="students connect", reqired_role="Lehrer"
        )

    @app_commands.command(
        name='disconnect',
        description='Trennt ein Mitglied von einem bestehenden Schüler.'
    )
    @app_commands.describe(
        student_id='Der Schüler, von dem getrennt werden soll',
        new_account_id='Das Mitglied, das getrennt werden soll'
    )
    @app_commands.checks.has_role('Lehrer')
    async def disconnect(self, interaction: discord.Interaction, student_id: str, new_account_id: str):
        student = env.get_member(interaction, student_id)
        new_account = env.get_member(interaction, new_account_id)

        await interaction.response.defer(thinking=True)
        await coord.disconnect_student(
            interaction=interaction,
            student=student,
            other_account=new_account
        )

        await interaction.followup.send(
            env.success_response(f"Schüler {new_account.mention} von {student.mention} getrennt")
        )

    @disconnect.autocomplete('student_id')
    async def disconnect_member_id_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return env.filter_members_for_autocomplete(
            interaction, current, env.is_student
        )

    @disconnect.autocomplete('new_account_id')
    async def disconnect_other_id_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return env.filter_members_for_autocomplete(
            interaction, current, lambda m: env.is_student(m) and env.is_subuser(m), hideSubmembers=False
        )

    @disconnect.error
    async def disconnect_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        await env.handle_app_command_error(
            interaction, error, command_name="students disconnect", reqired_role="Lehrer"
        )

    # endregion Connections

    # region Rename

    @app_commands.command(
        name='rename',
        description='Benennt einen Schüler um.'
    )
    @app_commands.describe(
        student_id='Der Schüler, der umbenannt werden soll',
        new_name='Der neue Name des Schülers'
    )
    @app_commands.checks.has_role('Lehrer')
    async def rename(self, interaction: discord.Interaction, student_id: str, new_name: str):
        student = env.get_member(interaction, student_id)

        await interaction.response.defer(thinking=True)
        old_name = await coord.rename_student(
            interaction=interaction,
            student=student,
            new_name=new_name
        )

        await interaction.followup.send(
            env.success_response(f"Schüler {student.mention} umbenannt (ehemals `{old_name}`)")
        )

    @rename.autocomplete('student_id')
    async def rename_member_id_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return env.filter_members_for_autocomplete(
            interaction, current,
            lambda s: env.is_teacher_student_connected(t, s) if isinstance(t := interaction.user, discord.Member) else False,
            hideSubmembers=False
        )

    @rename.error
    async def rename_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        await env.handle_app_command_error(
            interaction, error, command_name="students rename", reqired_role="Lehrer"
        )

    # endregion Rename

    # region Sort

    @app_commands.command(
        name='sort',
        description='Sortiert die Kanäle in der Lehrerkategorie.'
    )
    @app_commands.checks.has_role('Lehrer')
    async def sort(self, interaction: discord.Interaction):
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                env.failure_response('Dieser Befehl kann nur von einem Lehrer ausgeführt werden')
            )
            return

        await interaction.response.defer(thinking=True)
        await coord.sort_channels(
            interaction=interaction,
            teacher=interaction.user
        )

        await interaction.followup.send(
            env.success_response("Kanäle sortiert")
        )

    @sort.error
    async def sort_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        await env.handle_app_command_error(
            interaction, error, command_name="students sort", reqired_role="Lehrer"
        )

    # endregion Sort


async def setup(bot):
    bot.tree.add_command(
        StudentsGroup(
            name="students",
            description="Befehle für Schüler"
        )
    )
    print('[Group] StudentsGroup loaded')
