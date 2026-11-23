"""Persistence helpers: moving DataFrames in and out of SQLite.

Table data is stored as CSV text (simple, portable, beginner-friendly) plus a
JSON map of column roles so types survive a save/load round-trip.
"""
import io
import json
from typing import Dict, List, Tuple

import pandas as pd

from database import now_iso
from services.dataframe import (ROLE_DATETIME, VALID_ROLES, ambiguous_dates,
                                apply_roles, coercion_losses)

META_COLS = ("id", "name", "description", "rows", "cols", "created_at", "updated_at")


def dataset_meta(row: dict) -> dict:
    return {k: row[k] for k in META_COLS}


def save_dataframe(conn, dataset_id: int, df: pd.DataFrame, roles: Dict[str, str],
                   snapshot_original: bool = False) -> None:
    """Write the DataFrame back to the datasets table."""
    csv_text = df.to_csv(index=False)
    roles_json = json.dumps(roles)
    if snapshot_original:
        conn.execute(
            "UPDATE datasets SET data=?, original_data=?, column_roles=?, original_roles=?, "
            "rows=?, cols=?, updated_at=? WHERE id=?",
            (csv_text, csv_text, roles_json, json.dumps(roles),
             len(df), len(df.columns), now_iso(), dataset_id),
        )
    else:
        conn.execute(
            "UPDATE datasets SET data=?, column_roles=?, rows=?, cols=?, updated_at=? WHERE id=?",
            (csv_text, roles_json, len(df), len(df.columns), now_iso(), dataset_id),
        )


def load_dataframe(row: dict) -> Tuple[pd.DataFrame, Dict[str, str]]:
    """Read a dataset row back into a DataFrame with the saved column roles."""
    text = row.get("data") or ""
    if not text.strip():
        return pd.DataFrame(), {}
    df = pd.read_csv(io.StringIO(text))
    roles = json.loads(row.get("column_roles") or "{}")
    df = apply_roles(df, roles)
    return df, roles


def load_frame_with_losses(text: str, roles_json: str) -> Tuple[pd.DataFrame, Dict[str, str], Dict[str, List[dict]], Dict[str, dict]]:
    """Decode stored CSV text + roles, reporting two things profiling must know
    about the RAW text (they are invisible after coercion):

    - ``losses``:    column -> values destroyed by role coercion ("1O50" in a
      numeric column), so invalid entries can be flagged, not silently nulled
    - ``ambiguous``: column -> {"count": n, "examples": [...]} date strings
      that could be read day-first or month-first (12-05-2024). pandas would
      coerce them month-first at load, so those columns are deliberately LEFT
      AS TEXT (role stays datetime) until the user confirms the convention.
    """
    if not (text or "").strip():
        return pd.DataFrame(), {}, {}, {}
    raw = pd.read_csv(io.StringIO(text))
    roles = json.loads(roles_json or "{}")
    losses: Dict[str, List[dict]] = {}
    ambiguous: Dict[str, dict] = {}
    for c in raw.columns:
        role = roles.get(c)
        if role not in VALID_ROLES:
            continue  # untyped columns are never coerced, so nothing is lost
        lost = coercion_losses(raw[c], role)
        if lost:
            losses[c] = lost
        if role == ROLE_DATETIME and not pd.api.types.is_datetime64_any_dtype(raw[c]):
            n_amb, examples = ambiguous_dates(raw[c])
            if n_amb:
                ambiguous[c] = {"count": n_amb, "examples": examples}
    # ambiguous date columns keep their raw text (the month-first decision has
    # NOT been made yet); everything else is coerced normally
    coerce_roles = dict(roles)
    for c in ambiguous:
        coerce_roles[c] = "text"
    df = apply_roles(raw, coerce_roles)
    return df, roles, losses, ambiguous


def load_dataframe_with_losses(row: dict) -> Tuple[pd.DataFrame, Dict[str, str], Dict[str, List[dict]], Dict[str, dict]]:
    """Loss/ambiguity-aware load of a dataset row (see load_frame_with_losses)."""
    return load_frame_with_losses(row.get("data") or "", row.get("column_roles") or "{}")
