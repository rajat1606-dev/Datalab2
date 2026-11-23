"""CleanFlow ELT Pipeline endpoints.

Routes (all under /api/cleanflow):
    POST /datasets/{id}/pipeline/preview   dry-run steps, capture per-step state
    POST /datasets/{id}/pipeline/run       run steps, save result as a NEW dataset
    GET  /pipelines                        list saved pipeline configurations
    POST /pipelines                        save a reusable pipeline
    GET  /pipelines/{id}                   one saved pipeline (with steps)
    PUT  /pipelines/{id}                   update name/description/steps
    DELETE /pipelines/{id}                 delete a saved pipeline
    GET  /runs                             recent pipeline runs (status history)

Running a pipeline NEVER mutates the source dataset: the cleaned result is
stored as a separate dataset so the original upload stays untouched.
"""
import json

from fastapi import APIRouter, HTTPException, Request

from database import add_history, get_conn, now_iso, query_all, query_one
from models_cleanflow import CFPipelinePreviewIn, CFPipelineRunIn, CFPipelineSaveIn
from services import session as sess
from services.cleanflow.cleaner import is_destructive
from services.cleanflow.pipeline import pipeline_summary, run_steps
from services.dataframe import DataError, column_meta, infer_roles
from services.store import dataset_meta, load_dataframe, save_dataframe

router = APIRouter(prefix="/api/cleanflow", tags=["cleanflow-pipeline"])


def _fetch_dataset(dataset_id: int, request: Request) -> dict:
    row = query_one("SELECT * FROM datasets WHERE id=?", (dataset_id,))
    if not row or not sess.owns_row(row, request):
        raise HTTPException(status_code=404, detail="Dataset not found.")
    return row


def _run_record(conn, request, pipeline_id, pipeline_name, row, summary, results,
                result_id=None, result_name=None):
    conn.execute(
        "INSERT INTO pipeline_runs (pipeline_id, pipeline_name, dataset_id, dataset_name, "
        "result_id, result_name, status, steps_total, steps_ok, rows_in, rows_out, detail, "
        "created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (pipeline_id, pipeline_name or "", row["id"], row["name"], result_id, result_name or "",
         summary["status"], summary["steps_total"], summary["steps_ok"],
         summary["rows_in"], summary["rows_out"], json.dumps(results, default=str), now_iso()),
    )


@router.post("/datasets/{dataset_id}/pipeline/preview")
def pipeline_preview(dataset_id: int, payload: CFPipelinePreviewIn, request: Request):
    row = _fetch_dataset(dataset_id, request)
    df, roles = load_dataframe(row)
    try:
        _final_df, _final_roles, results = run_steps(
            df, roles, [s.model_dump() for s in payload.steps], enforce_approval=False)
    except DataError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"steps": results, "summary": pipeline_summary(results),
            "destructive_steps": [i + 1 for i, s in enumerate(payload.steps)
                                  if is_destructive(s.model_dump())]}


@router.post("/datasets/{dataset_id}/pipeline/run")
def pipeline_run(dataset_id: int, payload: CFPipelineRunIn, request: Request):
    row = _fetch_dataset(dataset_id, request)
    df, roles = load_dataframe(row)
    try:
        result_df, result_roles, results = run_steps(
            df, roles, [s.model_dump() for s in payload.steps], enforce_approval=False)
    except DataError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    summary = pipeline_summary(results)
    if summary["status"] != "ok" or result_df.empty:
        with get_conn() as conn:
            _run_record(conn, request, None, "ad-hoc", row, summary, results)
        failed = next((r for r in results if r["status"] == "error"), None)
        raise HTTPException(
            status_code=400,
            detail=(f"Pipeline failed at step {failed['index']} "
                    f"('{failed['label']}'): {failed['message']}" if failed
                    else "The pipeline produced an empty dataset."))

    result_name = (payload.result_name or f"{row['name']} · cleaned").strip()[:80]
    roles_final = infer_roles(result_df)
    ts = now_iso()
    csv_text = result_df.to_csv(index=False)
    sid = sess.get_session_id(request)
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO datasets (name, description, rows, cols, data, original_data, "
            "column_roles, original_roles, created_at, updated_at, session_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (result_name, f"ELT pipeline result from '{row['name']}' "
                          f"({summary['steps_ok']} step(s))",
             len(result_df), len(result_df.columns), csv_text, csv_text,
             json.dumps(roles_final), json.dumps(roles_final), ts, ts, sid),
        )
        result_id = int(cur.lastrowid)
        add_history(conn, result_id, result_name, "created",
                    f"ELT pipeline output — {len(result_df)} rows, {len(result_df.columns)} columns")
        add_history(conn, dataset_id, row["name"], "cleanflow-pipeline",
                    f"Ran a {summary['steps_ok']}-step pipeline → '{result_name}'")
        _run_record(conn, request, None, "ad-hoc", row, summary, results,
                    result_id=result_id, result_name=result_name)

    return {
        "summary": {**summary, "steps": results},
        "result": {**dataset_meta(query_one("SELECT * FROM datasets WHERE id=?", (result_id,))),
                   "columns": column_meta(result_df, roles_final)},
    }


@router.get("/pipelines")
def list_pipelines(request: Request):
    where, params = sess.scope_filter(request, alias="p")
    rows = query_all(
        "SELECT p.id, p.name, p.description, p.created_at, p.updated_at, "
        "json_array_length(p.steps) AS steps_count "
        "FROM pipelines p WHERE 1=1 " + where + " ORDER BY p.updated_at DESC", tuple(params))
    return {"pipelines": rows}


@router.post("/pipelines", status_code=201)
def save_pipeline(payload: CFPipelineSaveIn, request: Request):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Pipeline name cannot be empty.")
    steps_json = json.dumps([s.model_dump() for s in payload.steps])
    ts = now_iso()
    sid = sess.get_session_id(request)
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO pipelines (session_id, name, description, steps, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)", (sid, name, payload.description, steps_json, ts, ts))
        pipeline_id = int(cur.lastrowid)
    return {"id": pipeline_id, "name": name, "description": payload.description,
            "steps_count": len(payload.steps), "created_at": ts, "updated_at": ts}


@router.get("/pipelines/{pipeline_id}")
def get_pipeline(pipeline_id: int, request: Request):
    row = query_one("SELECT * FROM pipelines WHERE id=?", (pipeline_id,))
    if not row or not sess.owns_row(row, request):
        raise HTTPException(status_code=404, detail="Pipeline not found.")
    try:
        steps = json.loads(row["steps"] or "[]")
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Saved pipeline is corrupted.")
    return {k: row[k] for k in ("id", "name", "description", "created_at", "updated_at")} | \
           {"steps": steps, "steps_count": len(steps)}


@router.put("/pipelines/{pipeline_id}")
def update_pipeline(pipeline_id: int, payload: CFPipelineSaveIn, request: Request):
    row = query_one("SELECT * FROM pipelines WHERE id=?", (pipeline_id,))
    if not row or not sess.owns_row(row, request):
        raise HTTPException(status_code=404, detail="Pipeline not found.")
    steps_json = json.dumps([s.model_dump() for s in payload.steps])
    with get_conn() as conn:
        conn.execute("UPDATE pipelines SET name=?, description=?, steps=?, updated_at=? WHERE id=?",
                     (payload.name.strip() or row["name"], payload.description,
                      steps_json, now_iso(), pipeline_id))
    return get_pipeline(pipeline_id, request)


@router.delete("/pipelines/{pipeline_id}")
def delete_pipeline(pipeline_id: int, request: Request):
    row = query_one("SELECT * FROM pipelines WHERE id=?", (pipeline_id,))
    if not row or not sess.owns_row(row, request):
        raise HTTPException(status_code=404, detail="Pipeline not found.")
    with get_conn() as conn:
        conn.execute("DELETE FROM pipelines WHERE id=?", (pipeline_id,))
    return {"ok": True}


@router.get("/runs")
def list_runs(request: Request, limit: int = 30):
    rows = query_all(
        "SELECT id, pipeline_id, pipeline_name, dataset_id, dataset_name, result_id, "
        "result_name, status, steps_total, steps_ok, rows_in, rows_out, created_at "
        f"FROM pipeline_runs ORDER BY id DESC LIMIT {min(max(limit, 1), 200)}")
    return {"runs": rows}


@router.get("/runs/{run_id}")
def get_run(run_id: int, request: Request):
    row = query_one("SELECT * FROM pipeline_runs WHERE id=?", (run_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Run not found.")
    try:
        detail = json.loads(row["detail"] or "[]")
    except json.JSONDecodeError:
        detail = []
    out = {k: row[k] for k in row if k != "detail"}
    return {**out, "steps": detail}
