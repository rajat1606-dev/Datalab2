"""Optional per-browser-session isolation for CleanFlow (DataLab 2.0).

The frontend sends an ``X-Session-Id`` header with every request (a UUID kept
in localStorage). Datasets/pipelines created while a session id is present are
stamped with it and only listed/loaded for that session; rows created without
a session (legacy DataLab data) remain visible to everyone, so nothing breaks
for existing clients that never send the header.
"""
from fastapi import Request

MAX_SESSION_LEN = 64


def get_session_id(request: Request) -> str:
    """Read the caller's session id (empty when the client does not send one)."""
    raw = request.headers.get("x-session-id") or ""
    cleaned = "".join(ch for ch in raw if ch.isalnum() or ch in "-_")
    return cleaned[:MAX_SESSION_LEN]


def scope_filter(request: Request, alias: str = "") -> tuple:
    """SQL fragment + params that restrict rows to this session (or shared rows).

    Returns ("", []) when the client has no session id -> legacy behaviour.
    """
    sid = get_session_id(request)
    if not sid:
        return "", []
    col = f"{alias}.session_id" if alias else "session_id"
    return f"AND ({col} = ? OR {col} = '')", [sid]


def owns_row(row: dict, request: Request) -> bool:
    """True when the caller may see this dataset/pipeline row."""
    sid = get_session_id(request)
    row_sid = (row.get("session_id") or "") if isinstance(row, dict) else ""
    return not sid or row_sid in ("", sid)
