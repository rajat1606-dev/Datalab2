"""History endpoints: the analysis/cleaning activity log."""
from fastapi import APIRouter, Query

from database import get_conn, query_all

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("")
def list_history(dataset_id: int = Query(None), limit: int = Query(100, ge=1, le=500)):
    if dataset_id:
        rows = query_all(
            "SELECT * FROM history WHERE dataset_id=? ORDER BY id DESC LIMIT ?",
            (dataset_id, limit),
        )
    else:
        rows = query_all("SELECT * FROM history ORDER BY id DESC LIMIT ?", (limit,))
    return {"history": rows}


@router.delete("")
def clear_history():
    with get_conn() as conn:
        conn.execute("DELETE FROM history")
    return {"ok": True}
