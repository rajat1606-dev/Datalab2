"""Cleaning endpoint: applies a batch of cleaning operations to a dataset."""
import json

from fastapi import APIRouter, HTTPException, Request

from database import add_history, get_conn, query_one
from models import CleanIn
from services import session as sess
from services.cleaning import apply_operations, snapshot
from services.store import dataset_meta, load_dataframe, save_dataframe

router = APIRouter(prefix="/api/datasets", tags=["cleaning"])


@router.post("/{dataset_id}/clean")
def clean_dataset(dataset_id: int, payload: CleanIn, request: Request):
    row = query_one("SELECT * FROM datasets WHERE id=?", (dataset_id,))
    if not row or not sess.owns_row(row, request):
        raise HTTPException(status_code=404, detail="Dataset not found.")
    df, roles = load_dataframe(row)
    if df.empty:
        raise HTTPException(status_code=400, detail="This dataset has no rows to clean.")

    before = snapshot(df)
    try:
        df2, roles2, log = apply_operations(df, roles, [op.model_dump() for op in payload.operations])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    after = snapshot(df2)
    summary = "; ".join(op["detail"] for op in log if op["affected"]) or "No changes were needed"
    with get_conn() as conn:
        save_dataframe(conn, dataset_id, df2, roles2)
        add_history(conn, dataset_id, row["name"], "cleaned", summary)
    return {
        "before": before,
        "after": after,
        "operations": log,
        "summary": summary,
        "dataset": dataset_meta(query_one("SELECT * FROM datasets WHERE id=?", (dataset_id,))),
    }
