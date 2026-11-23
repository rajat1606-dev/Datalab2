"""Statistical analysis: per-column summary statistics and correlation matrix."""
from typing import Dict, Optional

import pandas as pd

from services.dataframe import ROLE_DATETIME, ROLE_NUMERIC, ROLE_TEXT


def _f(v, nd: int = 4) -> Optional[float]:
    """JSON-safe rounded float (None when missing)."""
    try:
        if v is None or pd.isna(v):
            return None
    except (TypeError, ValueError):
        return None
    return round(float(v), nd)


def _modes(s: pd.Series, k: int = 3):
    """Most frequent values (all values tied with the max frequency)."""
    if pd.api.types.is_datetime64_any_dtype(s):
        s = s.dropna().astype(str)  # stringify before counting (NaT would become a value)
    vc = s.value_counts(dropna=True)
    if vc.empty:
        return []

    def fmt(v):
        if isinstance(v, float) and v.is_integer():
            return str(int(v))
        return str(v)

    top = vc[vc == vc.iloc[0]]
    return [fmt(v) for v in top.index[:k]]


def compute_stats(df: pd.DataFrame, roles: Dict[str, str]) -> dict:
    summary = []
    for col in df.columns:
        s = df[col]
        role = roles.get(col, ROLE_TEXT)
        entry = {
            "column": col,
            "role": role,
            "count": int(s.notna().sum()),
            "missing": int(s.isna().sum()),
            "unique": int(s.nunique(dropna=True)),
        }
        if role == ROLE_NUMERIC and pd.api.types.is_numeric_dtype(s):
            d = s.describe()
            entry.update({
                "mean": _f(d["mean"]),
                "median": _f(d["50%"]),
                "std": _f(d["std"]),
                "min": _f(d["min"]),
                "q25": _f(d["25%"]),
                "q75": _f(d["75%"]),
                "max": _f(d["max"]),
                "modes": _modes(s),
                "skew": _f(s.skew()),
            })
        elif role == ROLE_DATETIME:
            entry.update({
                "min": str(s.min()) if s.notna().any() else None,
                "max": str(s.max()) if s.notna().any() else None,
                "modes": _modes(s.astype(str)),
            })
        else:
            entry["modes"] = _modes(s)
            vc = s.value_counts(dropna=True)
            if not vc.empty:
                entry.update({"top": str(vc.index[0]), "freq": int(vc.iloc[0])})
        summary.append(entry)

    corr = None
    nums = [c for c in df.columns
            if roles.get(c) == ROLE_NUMERIC and pd.api.types.is_numeric_dtype(df[c])]
    if len(nums) >= 2:
        m = df[nums].corr().round(4)
        corr = {
            "columns": nums,
            "matrix": [[None if pd.isna(v) else float(v) for v in row] for row in m.values],
        }
    return {"summary": summary, "correlation": corr}
