"""Dataset endpoints: upload, manual entry, CRUD, dashboard, preview, restore."""
import math
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile

from database import add_history, get_conn, now_iso, query_all, query_one
from models import DatasetMetaIn, ManualDataIn, ManualDatasetIn
from services import session as sess
from services.dataframe import (
    MAX_UPLOAD_BYTES,
    DataError,
    build_manual_df,
    column_meta,
    dataframe_rows,
    infer_roles,
    parse_upload,
)
from services.store import dataset_meta, load_dataframe, save_dataframe

router = APIRouter(prefix="/api/datasets", tags=["datasets"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fetch_row(dataset_id: int, request: Request = None) -> dict:
    row = query_one("SELECT * FROM datasets WHERE id=?", (dataset_id,))
    if not row or (request is not None and not sess.owns_row(row, request)):
        raise HTTPException(status_code=404, detail="Dataset not found.")
    return row


def _validate_manual_payload(payload: ManualDataIn) -> None:
    if len(payload.rows) > 20000:
        raise HTTPException(status_code=400, detail="Manual datasets are limited to 20,000 rows.")
    n = len(payload.columns)
    for i, row in enumerate(payload.rows):
        if len(row) != n:
            raise HTTPException(
                status_code=400,
                detail=f"Row {i + 1} has {len(row)} values but the table has {n} column(s).",
            )


def _insert_dataset(conn, name: str, description: str, df, roles, session_id: str = "") -> int:
    csv_text = df.to_csv(index=False)
    roles_json = __import__("json").dumps(roles)
    ts = now_iso()
    cur = conn.execute(
        "INSERT INTO datasets (name, description, rows, cols, data, original_data, "
        "column_roles, original_roles, created_at, updated_at, session_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (name, description, len(df), len(df.columns), csv_text, csv_text,
         roles_json, roles_json, ts, ts, session_id),
    )
    return int(cur.lastrowid)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("")
def list_datasets(request: Request):
    # Session isolation: with an X-Session-Id header only that session's (and
    # legacy shared) datasets are listed; without it, behaviour is unchanged.
    where, params = sess.scope_filter(request, alias="d")
    rows = query_all(
        "SELECT id, name, description, rows, cols, created_at, updated_at "
        "FROM datasets d WHERE 1=1 " + where + " ORDER BY updated_at DESC", tuple(params))
    return {"datasets": rows}


@router.post("/upload", status_code=201)
async def upload_dataset(request: Request, file: UploadFile = File(...),
                         name: str = Form(default="")):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file was provided.")
    raw = await file.read()
    if len(raw) == 0:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 15 MB).")
    try:
        df = parse_upload(file.filename, raw)
    except DataError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    roles = infer_roles(df)
    display_name = (name or Path(file.filename).stem or "Dataset").strip()[:80] or "Dataset"
    with get_conn() as conn:
        dataset_id = _insert_dataset(conn, display_name, f"Uploaded from {file.filename}", df,
                                     roles, session_id=sess.get_session_id(request))
        add_history(conn, dataset_id, display_name, "uploaded",
                    f"Uploaded '{file.filename}' — {len(df)} rows, {len(df.columns)} columns")
    return {**dataset_meta(_fetch_row(dataset_id)),
            "columns": column_meta(df, roles)}


@router.post("/manual", status_code=201)
def create_manual_dataset(payload: ManualDatasetIn, request: Request):
    _validate_manual_payload(payload)
    colspecs = [{"name": c.name, "type": c.type} for c in payload.columns]
    try:
        df, warnings = build_manual_df(colspecs, payload.rows)
    except DataError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    roles = infer_roles(df)
    with get_conn() as conn:
        dataset_id = _insert_dataset(conn, payload.name.strip(), payload.description, df, roles,
                                     session_id=sess.get_session_id(request))
        add_history(conn, dataset_id, payload.name.strip(), "created",
                    f"Created manually — {len(df)} rows, {len(df.columns)} columns")
    return {**dataset_meta(_fetch_row(dataset_id)), "columns": column_meta(df, roles),
            "warnings": warnings}


@router.get("/{dataset_id}")
def get_dataset(dataset_id: int, request: Request):
    return dataset_meta(_fetch_row(dataset_id, request))


@router.put("/{dataset_id}")
def update_dataset(dataset_id: int, payload: DatasetMetaIn, request: Request):
    row = _fetch_row(dataset_id, request)
    name = (payload.name if payload.name is not None else row["name"]).strip()
    description = payload.description if payload.description is not None else row["description"]
    if not name:
        raise HTTPException(status_code=400, detail="Dataset name cannot be empty.")
    with get_conn() as conn:
        conn.execute("UPDATE datasets SET name=?, description=?, updated_at=? WHERE id=?",
                     (name, description, now_iso(), dataset_id))
        if name != row["name"]:
            add_history(conn, dataset_id, name, "renamed", f"Renamed '{row['name']}' → '{name}'")
    return dataset_meta(_fetch_row(dataset_id))


@router.delete("/{dataset_id}")
def delete_dataset(dataset_id: int, request: Request):
    row = _fetch_row(dataset_id, request)
    with get_conn() as conn:
        conn.execute("DELETE FROM datasets WHERE id=?", (dataset_id,))
        add_history(conn, None, row["name"], "deleted", f"Deleted dataset '{row['name']}'")
    return {"ok": True}


@router.put("/{dataset_id}/data")
def replace_dataset_data(dataset_id: int, payload: ManualDataIn, request: Request):
    """Replace the full table of an existing dataset (used by the editable grid)."""
    _fetch_row(dataset_id, request)
    _validate_manual_payload(payload)
    colspecs = [{"name": c.name, "type": c.type} for c in payload.columns]
    try:
        df, warnings = build_manual_df(colspecs, payload.rows)
    except DataError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    roles = infer_roles(df)
    with get_conn() as conn:
        save_dataframe(conn, dataset_id, df, roles, snapshot_original=True)
        add_history(conn, dataset_id, _fetch_row(dataset_id)["name"],
                    "edited", f"Edited data — now {len(df)} rows, {len(df.columns)} columns")
    return {**dataset_meta(_fetch_row(dataset_id)), "columns": column_meta(df, roles),
            "warnings": warnings}


@router.post("/{dataset_id}/restore")
def restore_original(dataset_id: int, request: Request):
    row = _fetch_row(dataset_id, request)
    if not (row["original_data"] or "").strip():
        raise HTTPException(status_code=400, detail="No original snapshot is stored for this dataset.")
    import io
    import pandas as pd
    from services.dataframe import apply_roles
    df = pd.read_csv(io.StringIO(row["original_data"]))
    roles = __import__("json").loads(row["original_roles"] or "{}")
    df = apply_roles(df, roles)
    with get_conn() as conn:
        save_dataframe(conn, dataset_id, df, roles)
        add_history(conn, dataset_id, row["name"], "restored",
                    "Restored the original (pre-cleaning) data")
    return dataset_meta(_fetch_row(dataset_id))


@router.get("/{dataset_id}/dashboard")
def dataset_dashboard(dataset_id: int, request: Request):
    row = _fetch_row(dataset_id, request)
    df, roles = load_dataframe(row)
    missing = int(df.isna().sum().sum())
    dup = int(df.duplicated().sum())
    role_counts = {"numeric": 0, "categorical": 0, "datetime": 0, "text": 0}
    for r in roles.values():
        if r in role_counts:
            role_counts[r] += 1
    return {
        **dataset_meta(row),
        "rows": len(df),
        "cols": len(df.columns),
        "missing_cells": missing,
        "missing_pct": round(100 * missing / max(len(df) * max(len(df.columns), 1), 1), 2),
        "duplicate_rows": dup,
        "memory_mb": round(float(df.memory_usage(deep=True).sum()) / 1_048_576, 3),
        "roles_summary": role_counts,
        "column_details": column_meta(df, roles),
    }


@router.get("/{dataset_id}/columns")
def dataset_columns(dataset_id: int, request: Request):
    row = _fetch_row(dataset_id, request)
    df, roles = load_dataframe(row)
    return {"columns": [{"name": c, "role": roles.get(c, "text")} for c in df.columns]}


@router.get("/{dataset_id}/preview")
def dataset_preview(dataset_id: int, request: Request, page: int = Query(1, ge=1),
                    page_size: int = Query(50, ge=1, le=100000)):
    row = _fetch_row(dataset_id, request)
    df, roles = load_dataframe(row)
    total = len(df)
    total_pages = max(1, math.ceil(total / page_size))
    page = min(page, total_pages)
    offset = (page - 1) * page_size
    return {
        **dataset_meta(row),
        "page": page,
        "page_size": page_size,
        "total_rows": total,
        "total_pages": total_pages,
        "columns": column_meta(df, roles),
        "rows": dataframe_rows(df, limit=page_size, offset=offset),
    }
