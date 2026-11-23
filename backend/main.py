"""DataLab API entry point.

Run from the backend folder:
    python -m uvicorn main:app --host 0.0.0.0 --port 3000

If ../frontend/dist exists (production build), the API also serves the React
app, so the whole platform runs on a single port.
"""
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from database import init_db, query_one
from routers import charts, cleaning, datasets, export, history, stats
from routers import cleanflow_core, cleanflow_pipeline, cleanflow_report

app = FastAPI(title="DataLab API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # the app is same-origin; CORS is open for dev tools/Capacitor
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()

app.include_router(datasets.router)
app.include_router(cleaning.router)
app.include_router(charts.router)
app.include_router(stats.router)
app.include_router(export.router)
app.include_router(history.router)

# CleanFlow (DataLab 2.0) — intelligent ELT & automated data cleaning
app.include_router(cleanflow_core.router)
app.include_router(cleanflow_pipeline.router)
app.include_router(cleanflow_report.router)


@app.get("/api/health")
def health():
    n = query_one("SELECT COUNT(*) AS n FROM datasets")["n"]
    p = query_one("SELECT COUNT(*) AS n FROM pipelines")["n"]
    return {"status": "ok", "app": "DataLab", "version": "2.0.0",
            "datasets": n, "pipelines": p, "cleanflow": True}


# --- Serve the built React app (production / preview) -----------------------
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"

if FRONTEND_DIST.exists():
    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found.")
        target = (FRONTEND_DIST / full_path).resolve()
        if full_path and target.is_file() and str(target).startswith(str(FRONTEND_DIST)):
            return FileResponse(target)
        return FileResponse(FRONTEND_DIST / "index.html")
