"""CleanFlow data-quality report + Export Center endpoints.

Routes (all under /api/cleanflow):
    GET  /datasets/{id}/report             before/after quality report (JSON)
    GET  /datasets/{id}/report/download    quality report as JSON or HTML file
    GET  /datasets/{id}/export             cleaned data as CSV / Excel / JSON
"""
import io
import json
import re

import pandas as pd
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from database import add_history, get_conn, query_all, query_one
from services import session as sess
from services.cleanflow.report import (build_report, operations_timeline,
                                       report_to_html_bytes, report_to_json_bytes)
from services.dataframe import sanitize_for_excel
from services.store import load_dataframe

router = APIRouter(prefix="/api/cleanflow", tags=["cleanflow-report"])

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _fetch_dataset(dataset_id: int, request: Request) -> dict:
    row = query_one("SELECT * FROM datasets WHERE id=?", (dataset_id,))
    if not row or not sess.owns_row(row, request):
        raise HTTPException(status_code=404, detail="Dataset not found.")
    return row


def _safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_")[:40] or "dataset"


@router.get("/datasets/{dataset_id}/report")
def quality_report(dataset_id: int, request: Request):
    row = _fetch_dataset(dataset_id, request)
    report = build_report(row)
    log_rows = query_all(
        "SELECT * FROM cleanflow_log WHERE dataset_id=? ORDER BY id DESC LIMIT 100",
        (dataset_id,))
    return {**report, "operations": operations_timeline(log_rows)}


@router.get("/datasets/{dataset_id}/report/download")
def download_quality_report(dataset_id: int, request: Request,
                            format: str = Query("json", pattern="^(json|html)$")):
    row = _fetch_dataset(dataset_id, request)
    report = build_report(row)
    log_rows = query_all(
        "SELECT * FROM cleanflow_log WHERE dataset_id=? ORDER BY id DESC LIMIT 100",
        (dataset_id,))
    timeline = operations_timeline(log_rows)
    safe = _safe_name(row["name"])
    if format == "html":
        body, media, ext = report_to_html_bytes(report, timeline), "text/html; charset=utf-8", "html"
    else:
        body, media, ext = report_to_json_bytes(report, timeline), "application/json", "json"
    with get_conn() as conn:
        add_history(conn, dataset_id, row["name"], "cleanflow-report",
                    f"Downloaded the data-quality report ({ext.upper()})")
    return StreamingResponse(io.BytesIO(body), media_type=media, headers={
        "Content-Disposition": f'attachment; filename="quality_report_{safe}.{ext}"',
        "Content-Length": str(len(body)),
    })


@router.get("/datasets/{dataset_id}/export")
def cleanflow_export(dataset_id: int, request: Request,
                     format: str = Query("csv", pattern="^(csv|xlsx|json)$")):
    row = _fetch_dataset(dataset_id, request)
    df, _roles = load_dataframe(row)
    if df.empty:
        raise HTTPException(status_code=400, detail="This dataset has no data to export.")

    safe = _safe_name(row["name"])
    buf = io.BytesIO()
    if format == "xlsx":
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            sanitize_for_excel(df).to_excel(writer, index=False, sheet_name="Data")
        media, ext = XLSX_MIME, "xlsx"
    elif format == "json":
        # dates become ISO-8601 strings; column names & dtypes are preserved
        df.to_json(buf, orient="records", date_format="iso", indent=2, force_ascii=False)
        media, ext = "application/json; charset=utf-8", "json"
    else:
        df.to_csv(buf, index=False)
        media, ext = "text/csv; charset=utf-8", "csv"
    size = buf.tell()
    buf.seek(0)

    with get_conn() as conn:
        add_history(conn, dataset_id, row["name"], "cleanflow-export",
                    f"CleanFlow: exported {len(df)} rows as {ext.upper()}")
    return StreamingResponse(
        buf, media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{safe}_cleaned.{ext}"',
                 "Content-Length": str(size)})
