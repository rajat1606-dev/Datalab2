"""Export endpoint: download the (processed) dataset as CSV or Excel."""
import io
import re

import pandas as pd
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from database import add_history, get_conn, query_one
from services import session as sess
from services.dataframe import sanitize_for_excel
from services.store import load_dataframe

router = APIRouter(prefix="/api/datasets", tags=["export"])

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/{dataset_id}/export")
def export_dataset(dataset_id: int, request: Request,
                   format: str = Query("csv", pattern="^(csv|xlsx)$"),
                   include_index: bool = Query(False)):
    row = query_one("SELECT * FROM datasets WHERE id=?", (dataset_id,))
    if not row or not sess.owns_row(row, request):
        raise HTTPException(status_code=404, detail="Dataset not found.")
    df, _ = load_dataframe(row)
    if df.empty:
        raise HTTPException(status_code=400, detail="This dataset has no data to export.")

    safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", row["name"]).strip("_")[:40] or "dataset"
    buf = io.BytesIO()
    if format == "xlsx":
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            sanitize_for_excel(df).to_excel(writer, index=include_index, sheet_name="Data")
        media, ext = XLSX_MIME, "xlsx"
    else:
        df.to_csv(buf, index=include_index)
        media, ext = "text/csv; charset=utf-8", "csv"
    size = buf.tell()
    buf.seek(0)

    with get_conn() as conn:
        add_history(conn, dataset_id, row["name"], "exported",
                    f"Exported {len(df)} rows as {ext.upper()}")

    return StreamingResponse(
        buf,
        media_type=media,
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}.{ext}"',
            "Content-Length": str(size),
        },
    )
