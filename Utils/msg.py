def error_msg(msg: str, error=None, code_issue: bool = True) -> str:
    return f"{'⚠️ [DEV]' if code_issue else '❌'} Fehler: {msg} {f'```{error}```' if error else ''}"


def success_msg(msg: str) -> str:
    return f"✅ {msg}"
