from .errors import CodeError


def error_msg(msg: str, error=None) -> str:
    return f"{'⚠️ [DEV]' if isinstance(error, CodeError) else '❌'} Fehler: {msg} {f'```{error}```' if error else ''}"


def success_msg(msg: str) -> str:
    return f"✅ {msg}"
