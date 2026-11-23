"""CleanFlow core endpoints: upload, profile, apply operations, undo.

Routes (all under /api/cleanflow):
    POST /datasets/upload                 multi-format upload (CSV/XLSX/XLS/JSON)
    GET  /datasets/{id}/profile           automatic profiling (read-only)
    POST /datasets/{id}/clean             apply approved cleaning operations
    POST /datasets/{id}/undo              undo the last applied batch
    GET  /ops                             operation registry for the UI
"""
import io
import json

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from database import add_history, get_conn, now_iso, query_all, query_one
from models_cleanflow import CFApplyIn
from services import session as sess
from services.cleanflow.cleaner import UNDO_LIMIT, apply_ops, is_destructive, ops_catalog
from services.cleanflow.parser import MAX_UPLOAD_BYTES, OK_EXTENSIONS, parse_cleanflow_upload
from services.cleanflow.profiler import profile_dataframe
from services.cleanflow.report import preview_changes
from services.dataframe import DataError, column_meta, infer_roles
from services.store import dataset_meta, load_dataframe, load_dataframe_with_losses, save_dataframe

router = APIRouter(prefix="/api/cleanflow", tags=["cleanflow"])


# ---------------------------------------------------------------------------
# shared helpers
# ---------------------------------------------------------------------------

def _fetch_dataset(dataset_id: int, request: Request) -> dict:
    row = query_one("SELECT * FROM datasets WHERE id=?", (dataset_id,))
    if not row or not sess.owns_row(row, request):
        raise HTTPException(status_code=404, detail="Dataset not found.")
    return row


def _cf_log(conn, request: Request, row: dict, action: str, ops: list,
            score_before, score_after, rows_before, rows_after, summary: str) -> None:
    conn.execute(
        "INSERT INTO cleanflow_log (session_id, dataset_id, dataset_name, action, ops, "
        "score_before, score_after, rows_before, rows_after, summary, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (sess.get_session_id(request), row["id"], row["name"], action,
         json.dumps(ops, default=str), score_before, score_after,
         rows_before, rows_after, summary, now_iso()),
    )


def _push_undo(conn, dataset_id: int, df, roles: dict) -> None:
    conn.execute(
        "INSERT INTO undo_stack (dataset_id, data, roles, created_at) VALUES (?, ?, ?, ?)",
        (dataset_id, df.to_csv(index=False), json.dumps(roles), now_iso()),
    )
    conn.execute(
        "DELETE FROM undo_stack WHERE dataset_id=? AND id NOT IN "
        "(SELECT id FROM undo_stack WHERE dataset_id=? ORDER BY id DESC LIMIT ?)",
        (dataset_id, dataset_id, UNDO_LIMIT),
    )


def _quick_profile(row: dict) -> dict:
    df, roles, _losses, _amb = load_dataframe_with_losses(row)
    p = profile_dataframe(df, roles, _losses, _amb)
    return {
        "overview": p["overview"],
        "scores": p["scores"],
        "issues_count": len(p["issues"]),
        "high_issues": sum(1 for i in p["issues"] if i["severity"] == "high"),
    }


# ---------------------------------------------------------------------------
# endpoints
# ---------------------------------------------------------------------------

@router.get("/ops")
def get_ops_catalog():
    """Operation registry: drives the Transform page & Pipeline Builder forms."""
    return {"operations": ops_catalog()}


@router.post("/datasets/upload", status_code=201)
async def cleanflow_upload(request: Request, file: UploadFile = File(...),
                           name: str = Form(default="")):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file was provided.")
    lower = file.filename.lower()
    if not lower.endswith(OK_EXTENSIONS):
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Accepted: .csv, .tsv, .txt, .xlsx, .xlsm, .xls, .json")
    raw = await file.read()
    if len(raw) == 0:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 15 MB).")
    try:
        df = parse_cleanflow_upload(file.filename, raw)
    except DataError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    roles = infer_roles(df)
    display_name = (name or file.filename.rsplit(".", 1)[0] or "Dataset").strip()[:80] or "Dataset"
    sid = sess.get_session_id(request)
    ts = now_iso()
    csv_text = df.to_csv(index=False)
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO datasets (name, description, rows, cols, data, original_data, "
            "column_roles, original_roles, created_at, updated_at, session_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (display_name, f"CleanFlow upload ({file.filename})", len(df), len(df.columns),
             csv_text, csv_text, json.dumps(roles), json.dumps(roles), ts, ts, sid),
        )
        dataset_id = int(cur.lastrowid)
        add_history(conn, dataset_id, display_name, "uploaded",
                    f"CleanFlow: uploaded '{file.filename}' — {len(df)} rows, {len(df.columns)} columns")
    row = query_one("SELECT * FROM datasets WHERE id=?", (dataset_id,))
    return {**dataset_meta(row), "columns": column_meta(df, roles),
            "profile": _quick_profile(row)}


@router.get("/datasets/{dataset_id}/profile")
def cleanflow_profile(dataset_id: int, request: Request):
    row = _fetch_dataset(dataset_id, request)
    df, roles, losses, amb = load_dataframe_with_losses(row)
    if df.empty:
        raise HTTPException(status_code=400, detail="This dataset is empty — nothing to profile.")
    report = profile_dataframe(df, roles, losses, amb)
    return {**dataset_meta(row), **report}


@router.post("/datasets/{dataset_id}/clean")
def cleanflow_clean(dataset_id: int, payload: CFApplyIn, request: Request):
    row = _fetch_dataset(dataset_id, request)
    df, roles, losses, amb = load_dataframe_with_losses(row)
    if df.empty:
        raise HTTPException(status_code=400, detail="This dataset has no rows to clean.")

    before_profile = profile_dataframe(df, roles, losses, amb)
    try:
        df2, roles2, logs = apply_ops(df, roles, [op.model_dump() for op in payload.operations],
                                      enforce_approval=True)
    except DataError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    after_profile = profile_dataframe(df2, roles2)

    summary = "; ".join(e["detail"] for e in logs if e["affected"]) or "No changes were needed"
    ops_serialized = [dict(e) for e in logs]
    with get_conn() as conn:
        _push_undo(conn, dataset_id, df, roles)  # snapshot BEFORE the change
        save_dataframe(conn, dataset_id, df2, roles2)
        add_history(conn, dataset_id, row["name"], "cleanflow-clean", summary)
        _cf_log(conn, request, row, "clean", ops_serialized,
                before_profile["overview"]["quality_score"],
                after_profile["overview"]["quality_score"],
                len(df), len(df2), summary)
    return {
        "before": before_profile["overview"],
        "after": after_profile["overview"],
        "changes": preview_changes(df, df2),
        "operations": ops_serialized,
        "summary": summary,
        "dataset": dataset_meta(query_one("SELECT * FROM datasets WHERE id=?", (dataset_id,))),
    }


@router.post("/datasets/{dataset_id}/undo")
def cleanflow_undo(dataset_id: int, request: Request):
    row = _fetch_dataset(dataset_id, request)
    snap = query_one(
        "SELECT * FROM undo_stack WHERE dataset_id=? ORDER BY id DESC LIMIT 1", (dataset_id,))
    if not snap:
        raise HTTPException(status_code=400, detail="There is nothing left to undo.")
    import pandas as pd
    from services.dataframe import apply_roles
    try:
        df = pd.read_csv(io.StringIO(snap["data"]))
        roles = json.loads(snap["roles"] or "{}")
    except (ValueError, json.JSONDecodeError):
        raise HTTPException(status_code=500, detail="The undo snapshot is corrupted.")
    df = apply_roles(df, roles)
    with get_conn() as conn:
        conn.execute("DELETE FROM undo_stack WHERE id=?", (snap["id"],))
        save_dataframe(conn, dataset_id, df, roles)
        add_history(conn, dataset_id, row["name"], "cleanflow-undo",
                    "Undid the last cleaning batch")
        _cf_log(conn, request, row, "undo", [],
                None, None, None, len(df), "Undid the last cleaning batch")
    updated = query_one("SELECT * FROM datasets WHERE id=?", (dataset_id,))
    return {"ok": True, "dataset": dataset_meta(updated),
            "profile": _quick_profile(updated)}


@router.get("/datasets/{dataset_id}/undo-count")
def cleanflow_undo_count(dataset_id: int, request: Request):
    _fetch_dataset(dataset_id, request)
    n = query_one("SELECT COUNT(*) AS n FROM undo_stack WHERE dataset_id=?", (dataset_id,))
    return {"count": n["n"] if n else 0}


@router.get("/history")
def cleanflow_history(request: Request, dataset_id: int = None,
                      limit: int = 100):
    where, params = "WHERE 1=1 ", []
    scope, scope_params = sess.scope_filter(request)
    where += scope
    params.extend(scope_params)
    if dataset_id:
        where += " AND dataset_id=?"
        params.append(dataset_id)
    rows = query_all(
        f"SELECT id, dataset_id, dataset_name, action, ops, score_before, score_after, "
        f"rows_before, rows_after, summary, created_at FROM cleanflow_log {where} "
        f"ORDER BY id DESC LIMIT {min(max(limit, 1), 500)}", tuple(params))
    out = []
    for r in rows:
        try:
            ops = json.loads(r.pop("ops") or "[]")
        except json.JSONDecodeError:
            ops = []
        out.append({**r, "operations": ops})
    return {"history": out}
