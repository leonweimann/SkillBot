import discord

from .errors import CodeError


def error_msg(msg: str, error=None) -> str:
    return f"{'⚠️ [DEV]' if isinstance(error, CodeError) else '❌'} Fehler: {msg} {f'```{error}```' if error else ''}"


def success_msg(msg: str) -> str:
    return f"✅ {msg}"


async def safe_respond(interaction: discord.Interaction, content: str, ephemeral=False):
    if interaction.response.is_done():
        await interaction.followup.send(content, ephemeral=ephemeral)
    else:
        await interaction.response.send_message(content, ephemeral=ephemeral)
