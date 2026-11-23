"""Chart endpoints: recommendations and figure generation."""
import json

from fastapi import APIRouter, HTTPException, Request

from database import add_history, get_conn, query_one
from models import ChartIn
from services import session as sess
from services.charts import build_figure
from services.dataframe import DataError
from services.recommend import recommend_charts
from services.store import load_dataframe

router = APIRouter(prefix="/api/datasets", tags=["charts"])


@router.get("/{dataset_id}/recommendations")
def get_recommendations(dataset_id: int, request: Request):
    row = query_one("SELECT * FROM datasets WHERE id=?", (dataset_id,))
    if not row or not sess.owns_row(row, request):
        raise HTTPException(status_code=404, detail="Dataset not found.")
    df, roles = load_dataframe(row)
    return {"recommendations": recommend_charts(df, roles)}


@router.post("/{dataset_id}/chart")
def generate_chart(dataset_id: int, payload: ChartIn, request: Request):
    row = query_one("SELECT * FROM datasets WHERE id=?", (dataset_id,))
    if not row or not sess.owns_row(row, request):
        raise HTTPException(status_code=404, detail="Dataset not found.")
    df, roles = load_dataframe(row)
    try:
        fig = build_figure(df, roles, payload.model_dump())
    except DataError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    parts = []
    if payload.x:
        parts.append(f"x={payload.x}")
    if payload.y:
        parts.append(f"y={payload.y}")
    where = ", ".join(parts) or "correlation matrix"
    with get_conn() as conn:
        add_history(conn, dataset_id, row["name"], "chart",
                    f"{payload.chart_type.title()} chart ({where})")
    return {
        "chart_type": payload.chart_type,
        "params": payload.model_dump(),
        "figure": json.loads(fig.to_json()),
    }
