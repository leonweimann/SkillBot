from discord import app_commands


class CodeError(app_commands.AppCommandError):
    pass


class UsageError(app_commands.AppCommandError):
    pass
