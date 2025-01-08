def error_msg(msg: str, code_issue: bool = True) -> str:
    return f"{'⚠️ [DEV]' if code_issue else '❌'} Fehler: {msg}"


def success_msg(msg: str) -> str:
    return f"✅ {msg}"
