"""Data cleaning operations: missing values, duplicates and type conversion.

Every operation is validated, applied to a copy of the DataFrame and described
in a log entry that the API returns to the UI (and writes to history).
"""
from typing import Dict, List, Tuple

import pandas as pd

from services.dataframe import (
    ROLE_CATEGORICAL,
    ROLE_DATETIME,
    ROLE_NUMERIC,
    ROLE_TEXT,
    DataError,
)

STRATEGIES = ("mean", "median", "mode", "ffill", "bfill", "constant")
TARGETS = ("number", "date", "text", "categorical")


def _require_columns(df: pd.DataFrame, cols: List[str]) -> None:
    for c in cols:
        if c not in df.columns:
            raise DataError(f"Column '{c}' does not exist in this dataset.")


def _lost_values(before: pd.Series, after: pd.Series) -> int:
    """Count non-null values that became null after a conversion."""
    return int((before.notna() & after.isna()).sum())


def apply_operations(df: pd.DataFrame, roles: Dict[str, str], operations: List[dict]
                     ) -> Tuple[pd.DataFrame, Dict[str, str], List[dict]]:
    df = df.copy()
    roles = dict(roles)
    log: List[dict] = []

    for op in operations:
        kind = op.get("type")
        cols = list(op.get("columns") or [])
        if cols:
            _require_columns(df, cols)

        if kind == "fill_missing":
            strategy = op.get("strategy")
            if strategy not in STRATEGIES:
                raise DataError(f"Unknown fill strategy '{strategy}'.")
            if not cols:
                raise DataError("Select at least one column to fill missing values.")
            filled = 0
            for c in cols:
                s = df[c]
                before = int(s.isna().sum())
                if before == 0:
                    continue
                if strategy in ("mean", "median"):
                    if roles.get(c) != ROLE_NUMERIC or not pd.api.types.is_numeric_dtype(s):
                        raise DataError(
                            f"Column '{c}' is not numeric, so it cannot be filled with "
                            f"'{strategy}'. Convert it to a number first."
                        )
                    df[c] = s.fillna(s.mean() if strategy == "mean" else s.median())
                elif strategy == "mode":
                    modes = s.mode(dropna=True)
                    if not modes.empty:
                        df[c] = s.fillna(modes.iloc[0])
                elif strategy == "ffill":
                    df[c] = s.ffill()
                elif strategy == "bfill":
                    df[c] = s.bfill()
                elif strategy == "constant":
                    df[c] = s.fillna(op.get("value"))
                filled += before - int(df[c].isna().sum())
            log.append({"operation": "fill_missing",
                        "detail": f"Filled {filled} missing cell(s) using '{strategy}'",
                        "affected": filled})

        elif kind == "drop_missing":
            before = len(df)
            df = df.dropna(subset=cols or None, how=op.get("how") or "any")
            removed = before - len(df)
            if df.empty and removed > 0:
                raise DataError("That operation would remove every row, so it was rejected.")
            log.append({"operation": "drop_missing",
                        "detail": f"Removed {removed} row(s) containing missing values",
                        "affected": removed})

        elif kind == "drop_duplicates":
            before = len(df)
            df = df.drop_duplicates(subset=cols or None, keep=op.get("keep") or "first")
            removed = before - len(df)
            log.append({"operation": "drop_duplicates",
                        "detail": f"Removed {removed} duplicate row(s)",
                        "affected": removed})

        elif kind == "convert_type":
            target = op.get("target")
            if target not in TARGETS:
                raise DataError(f"Unknown target type '{target}'.")
            if not cols:
                raise DataError("Select at least one column to convert.")
            converted = 0
            for c in cols:
                s = df[c]
                if target == "number":
                    if pd.api.types.is_numeric_dtype(s):
                        roles[c] = ROLE_NUMERIC
                        converted += 1
                        continue
                    cleaned = s.astype(str).str.replace(",", "", regex=False).str.strip()
                    num = pd.to_numeric(cleaned, errors="coerce")
                    lost = _lost_values(s, num)
                    df[c] = num
                    roles[c] = ROLE_NUMERIC
                    converted += 1
                    if lost:
                        log.append({"operation": "convert_type",
                                    "detail": f"'{c}': {lost} value(s) could not be parsed as numbers and were set to missing",
                                    "affected": lost})
                elif target == "date":
                    try:
                        parsed = pd.to_datetime(s, errors="coerce", format="mixed")
                    except Exception:
                        parsed = pd.to_datetime(s.astype(str), errors="coerce", format="mixed")
                    lost = _lost_values(s, parsed)
                    df[c] = parsed
                    roles[c] = ROLE_DATETIME
                    converted += 1
                    if lost:
                        log.append({"operation": "convert_type",
                                    "detail": f"'{c}': {lost} value(s) could not be parsed as dates and were set to missing",
                                    "affected": lost})
                elif target == "text":
                    df[c] = s.astype(str).where(s.notna(), None)
                    roles[c] = ROLE_TEXT
                    converted += 1
                elif target == "categorical":
                    roles[c] = ROLE_CATEGORICAL
                    converted += 1
            log.append({"operation": "convert_type",
                        "detail": f"Converted {converted} column(s) to '{target}'",
                        "affected": converted})

        else:
            raise DataError(f"Unknown operation '{kind}'.")

    return df, roles, log


def snapshot(df: pd.DataFrame) -> dict:
    """Headline numbers shown before/after a cleaning run."""
    return {
        "rows": int(len(df)),
        "missing_cells": int(df.isna().sum().sum()),
        "duplicate_rows": int(df.duplicated().sum()),
    }
