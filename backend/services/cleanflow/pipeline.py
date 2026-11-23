"""CleanFlow ELT pipeline engine.

A pipeline is an ordered list of CleanFlow operations (the same registry used
by Auto Clean / Transformation). The engine can:

  - ``preview_steps``  dry-run the sequence and capture the state after every
    step (status, row/col counts, first rows) without saving anything
  - ``run_steps``      execute the sequence end-to-end (used when saving the
    result as a new dataset)

A failed step stops the run and is reported with its error message; earlier
steps keep their captured previews so users can inspect how far it got.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

import pandas as pd

from services.cleanflow.cleaner import OP_META, apply_ops
from services.cleanflow.profiler import profile_dataframe
from services.dataframe import DataError, dataframe_rows

MAX_STEPS = 40
PREVIEW_ROWS = 5


def _step_result(index: int, op: dict, status: str, df_in: pd.DataFrame,
                 df_out: pd.DataFrame = None, message: str = "",
                 affected: int = 0, roles_out: Dict[str, str] = None) -> dict:
    meta = OP_META.get(op.get("type"), {})
    res = {
        "index": index,
        "op": op.get("type"),
        "label": meta.get("label", op.get("type")),
        "status": status,
        "rows_in": int(len(df_in)),
        "cols_in": int(len(df_in.columns)),
        "message": message,
        "affected": int(affected),
    }
    if df_out is not None:
        res.update({
            "rows_out": int(len(df_out)),
            "cols_out": int(len(df_out.columns)),
            "columns": [str(c) for c in df_out.columns],
            "preview": dataframe_rows(df_out.head(PREVIEW_ROWS)),
        })
        profile = profile_dataframe(df_out.head(200), roles_out or {})
        res["quality_score"] = profile["overview"]["quality_score"]
    return res


def run_steps(df: pd.DataFrame, roles: Dict[str, str], steps: List[dict],
              enforce_approval: bool = False
              ) -> Tuple[pd.DataFrame, Dict[str, str], List[dict]]:
    """Execute steps in order; stops at the first failing step."""
    if not steps:
        raise DataError("The pipeline has no steps to run.")
    if len(steps) > MAX_STEPS:
        raise DataError(f"Pipelines are limited to {MAX_STEPS} steps.")
    if df.empty:
        raise DataError("This dataset has no rows to process.")

    out, out_roles = df.copy(), dict(roles)
    results: List[dict] = []
    for i, op in enumerate(steps, start=1):
        if not isinstance(op, dict) or not op.get("type"):
            results.append(_step_result(i, op if isinstance(op, dict) else {}, "error", out,
                                        message="Invalid step definition."))
            break
        try:
            new_df, new_roles, logs = apply_ops(out, out_roles, [op],
                                                enforce_approval=enforce_approval)
            out, out_roles = new_df, new_roles
            results.append(_step_result(i, op, "ok", df, out,
                                        message=logs[0]["detail"] if logs else "Done",
                                        affected=logs[0]["affected"] if logs else 0,
                                        roles_out=out_roles))
        except DataError as exc:
            results.append(_step_result(i, op, "error", df, out, message=str(exc)))
            break
    return out, out_roles, results


def pipeline_summary(results: List[dict]) -> dict:
    ok = sum(1 for r in results if r["status"] == "ok")
    failed = sum(1 for r in results if r["status"] == "error")
    status = "error" if failed else "ok"
    first, last = (results[0], results[-1]) if results else (None, None)
    return {
        "status": status,
        "steps_total": len(results),
        "steps_ok": ok,
        "steps_failed": failed,
        "rows_in": first["rows_in"] if first else 0,
        "rows_out": last["rows_out"] if last and last["status"] == "ok" else
                    (last["rows_in"] if last else 0),
    }
