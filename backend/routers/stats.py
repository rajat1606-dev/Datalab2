"""Statistics endpoint: summary statistics + correlation matrix."""
from fastapi import APIRouter, HTTPException, Request

from database import query_one
from services import session as sess
from services.stats import compute_stats
from services.store import load_dataframe

router = APIRouter(prefix="/api/datasets", tags=["stats"])


@router.get("/{dataset_id}/stats")
def dataset_stats(dataset_id: int, request: Request):
    row = query_one("SELECT * FROM datasets WHERE id=?", (dataset_id,))
    if not row or not sess.owns_row(row, request):
        raise HTTPException(status_code=404, detail="Dataset not found.")
    df, roles = load_dataframe(row)
    return compute_stats(df, roles)
