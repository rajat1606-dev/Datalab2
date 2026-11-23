"""Automatic data profiling for CleanFlow.

`profile_dataframe(df, roles, losses=None)` inspects a DataFrame and returns:
  - overview: rows, cols, memory, missing, duplicates, quality score + grade
  - per-column statistics (numeric / categorical / datetime / text)
  - a list of detected issues, each with a ready-to-apply recommendation

Detected problems: missing values, duplicate rows (exact + key-based when only
an identifier differs + text-normalized near-duplicates), incorrect data types,
invalid dates, **ambiguous dates** (12-05-2024 day-first vs month-first),
**invalid e-mail addresses**, **suspicious numeric values** (negatives,
impossible ranges such as age 150, extreme |z|>5), **invalid values destroyed
by type coercion** (e.g. the numeric string "1O50"), outliers (IQR + Z-score,
flag-first — treatment always needs approval), constant columns, empty rows /
columns, ID-like / high-cardinality columns and sentinel ("dirty") values such
as "N/A" or -999.

Nothing here modifies the data — profiling is strictly read-only.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from services.dataframe import (
    ROLE_CATEGORICAL,
    ROLE_DATETIME,
    ROLE_NUMERIC,
    ROLE_TEXT,
    ambiguous_dates as _shared_ambiguous_dates,
    json_value,
)

# Common sentinel values treated as "dirty" data (case-insensitive text match).
SENTINEL_TEXT = {"n/a", "na", "null", "none", "nil", "-", "--", "?", "error", "unknown", "nan"}
SENTINEL_NUMERIC = {-999, -9999, 9999, 99999}

WEIGHTS = {"completeness": 0.35, "uniqueness": 0.25, "validity": 0.25, "consistency": 0.15}

# A structurally valid e-mail address: local part @ domain with a real TLD.
# "kabir.khan@example" (no TLD) therefore fails.
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$")
LOOSE_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+$")

# 12-05-2024 / 12.05.24 — day and month could be swapped.
_AMBIGUOUS_DATE_RE = re.compile(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})$")

# Plausibility ranges for common column-name semantics.
_PLAUSIBLE_RANGES = (("age", (0, 120)), ("year", (1900, 2100)),
                     ("pct", (0, 100)), ("percent", (0, 100)))


def _grade(score: float) -> str:
    if score >= 90:
        return "Excellent"
    if score >= 75:
        return "Good"
    if score >= 55:
        return "Fair"
    if score >= 35:
        return "Poor"
    return "Critical"


def _round(v, nd: int = 4) -> Optional[float]:
    try:
        if v is None or pd.isna(v):
            return None
        return round(float(v), nd)
    except (TypeError, ValueError):
        return None


def _numeric_outliers(s: pd.Series, method: str, threshold: float):
    """Return (lower, upper, count, mask) for IQR or Z-score outlier bounds."""
    clean = s.dropna()
    if clean.empty:
        return None, None, 0, pd.Series(False, index=s.index)
    if method == "iqr":
        q1, q3 = clean.quantile(0.25), clean.quantile(0.75)
        iqr = q3 - q1
        spread = iqr
        center_span = (q1, q3)
        lo, hi = q1 - threshold * spread, q3 + threshold * spread
        if spread == 0:
            return None, None, 0, pd.Series(False, index=s.index)
    else:  # zscore
        mean, std = clean.mean(), clean.std()
        if not std or pd.isna(std):
            return None, None, 0, pd.Series(False, index=s.index)
        z = (clean - mean).abs() / std
        outliers = z[z > threshold]
        if clean.empty or len(outliers) == 0:
            lo = hi = None
        else:
            lo = float(clean[z <= threshold].min()) if (z <= threshold).any() else None
            hi = float(clean[z <= threshold].max()) if (z <= threshold).any() else None
        mask = s.index.isin(outliers.index)
        return lo, hi, int(len(outliers)), mask
    mask = ((s < lo) | (s > hi)) & s.notna()
    _ = center_span  # bounds context only
    return float(lo), float(hi), int(mask.sum()), mask.fillna(False)


def _sample(s: pd.Series, mask: pd.Series, limit: int = 8) -> List[dict]:
    """Flagged values with their row numbers: [{"row": 5, "value": 52}, ...]."""
    hits = s[mask]
    return [{"row": int(i) + 1, "value": json_value(v)} for i, v in hits.head(limit).items()]


def _text_issues(s: pd.Series) -> dict:
    """Whitespace / casing / sentinel problems on an object-dtype column."""
    vals = s.dropna()
    out = {"whitespace": 0, "case_variants": 0, "sentinels": 0, "sentinel_values": []}
    if vals.empty or not (pd.api.types.is_object_dtype(s) or pd.api.types.is_string_dtype(s)):
        return out
    strs = vals.astype(str)
    out["whitespace"] = int((strs != strs.str.strip()).sum() +
                            strs.str.contains(r"\s{2,}", regex=True).sum())
    lowered = strs.str.strip().str.lower()
    stripped = strs.str.strip()
    grouped: Dict[str, set] = {}
    for raw, low in zip(stripped, lowered):
        grouped.setdefault(low, set()).add(raw)
    variant_groups = [sorted(v) for v in grouped.values() if len(v) > 1]
    out["case_variants"] = len(variant_groups)
    out["variant_examples"] = [v for g in variant_groups[:2] for v in g[:2]][:2]
    low_set = lowered.isin(SENTINEL_TEXT)
    out["sentinels"] = int(low_set.sum())
    out["sentinel_values"] = sorted({str(v) for v, is_s in zip(stripped, low_set) if is_s})[:6]
    return out


def _looks_numeric_text(s: pd.Series) -> bool:
    vals = s.dropna().astype(str).str.replace(",", "", regex=False).str.strip()
    if vals.empty:
        return False
    try:
        parsed = pd.to_numeric(vals, errors="coerce")
    except Exception:
        return False
    return parsed.notna().mean() >= 0.9


def _invalid_date_count(s: pd.Series) -> int:
    """Rows that look like dates but fail to parse (role already says datetime)."""
    vals = s.dropna()
    if vals.empty:
        return 0
    strs = vals.astype(str)
    candidates = strs[strs.str.contains(r"[-/:]", regex=True)]
    if candidates.empty:
        return 0
    try:
        parsed = pd.to_datetime(candidates, errors="coerce", format="mixed")
    except Exception:
        return int(len(candidates))
    return int(parsed.isna().sum())


def _invalid_date_examples(s: pd.Series, limit: int = 4) -> List[str]:
    vals = s.dropna().astype(str).str.strip()
    vals = vals[vals.str.contains(r"[-/:]", regex=True)]
    if vals.empty:
        return []
    try:
        parsed = pd.to_datetime(vals, errors="coerce", format="mixed")
    except Exception:
        return [str(v) for v in vals.head(limit)]
    return [str(v) for v in vals[parsed.isna()].head(limit)]


def _ambiguous_dates(s: pd.Series) -> tuple:
    """Delegate to the shared detector (see services.dataframe.ambiguous_dates)."""
    return _shared_ambiguous_dates(s)


def _email_issues(s: pd.Series, col_name: str) -> dict:
    """Structural e-mail validation on a column that looks like it holds e-mails.

    A column is e-mail-like when its name mentions "mail" or when at least half
    of the non-empty values contain an @. Returns the invalid entries so they
    can be flagged (never corrected automatically).
    """
    out = {"is_email_col": False, "count": 0, "invalid": []}
    if not (pd.api.types.is_object_dtype(s) or pd.api.types.is_string_dtype(s)):
        return out
    vals = s.dropna().astype(str).str.strip()
    vals = vals[vals != ""]
    if vals.empty:
        return out
    loose = vals.str.match(LOOSE_EMAIL_RE)
    is_email_col = ("mail" in col_name.lower()) or (float(loose.mean()) >= 0.5)
    if not is_email_col:
        return out
    bad = vals[~vals.str.match(EMAIL_RE)]
    out["is_email_col"] = True
    out["count"] = int(len(bad))
    out["invalid"] = [{"row": int(i) + 1, "value": str(v)} for i, v in bad.head(8).items()]
    return out


def _suspicious_numeric_values(s: pd.Series, col_name: str) -> dict:
    """Flag (never change) numeric values that look wrong:

    - negative values (order counts, quantities and amounts usually are not)
    - values outside a plausible range implied by the column name
      (age outside 0-120, year outside 1900-2100, percentages outside 0-100)
    - statistical extremes with |z| > 5
    """
    out = {"negatives": [], "implausible": [], "extreme": [], "range": None}
    if not pd.api.types.is_numeric_dtype(s):
        return out
    clean = s.dropna()
    if clean.empty:
        return out
    neg = clean[clean < 0]
    if len(neg):
        out["negatives"] = [{"row": int(i) + 1, "value": json_value(v)}
                            for i, v in neg.head(8).items()]
    low = col_name.lower()
    for key, rng in _PLAUSIBLE_RANGES:
        if key in low:
            out["range"] = list(rng)
            bad = clean[(clean < rng[0]) | (clean > rng[1])]
            out["implausible"] = [{"row": int(i) + 1, "value": json_value(v)}
                                  for i, v in bad.head(8).items()]
            break
    std = clean.std()
    if std and not pd.isna(std) and len(clean) >= 5:
        z = ((clean - clean.mean()) / std).abs()
        ext = clean[z > 5]
        if len(ext):
            out["extreme"] = [{"row": int(i) + 1, "value": json_value(v)}
                              for i, v in ext.head(8).items()]
    return out


def _dup_example(df: pd.DataFrame, key_cols: List[str], id_cols: List[str]) -> str:
    """Human-readable example of one duplicate group ("C001 and C021 …")."""
    try:
        grp = df.loc[df.duplicated(subset=key_cols, keep=False)]
        if grp.empty:
            return ""
        first = grp.iloc[0]
        same = grp
        for c in key_cols:
            same = same[same[c] == first[c]]
        if len(same) < 2:
            return ""
        if id_cols and id_cols[0] in same.columns:
            a, b = same.iloc[0], same.iloc[1]
            return (f"Example: '{a[id_cols[0]]}' and '{b[id_cols[0]]}' "
                    "carry the same details.")
        return f"Example: rows {int(same.index[0]) + 1} and {int(same.index[1]) + 1}."
    except Exception:
        return ""


def profile_dataframe(df: pd.DataFrame, roles: Dict[str, str],
                      losses: Optional[Dict[str, List[dict]]] = None,
                      ambiguous: Optional[Dict[str, dict]] = None) -> dict:
    n_rows, n_cols = len(df), len(df.columns)
    total_cells = max(n_rows * n_cols, 1)
    memory_mb = round(float(df.memory_usage(deep=True).sum()) / 1_048_576, 3) if n_cols else 0.0
    duplicate_rows = int(df.duplicated().sum()) if n_rows else 0

    issues: List[dict] = []
    columns: List[dict] = []
    missing_cells = 0
    invalid_date_total = 0
    invalid_values_total = 0
    invalid_email_total = 0
    suspicious_total = 0
    ambiguous_total = 0
    whitespace_cells = 0
    case_variant_cols = 0
    text_cells = 0
    numeric_text_cols: List[str] = []
    outlier_cells_iqr = 0
    outlier_cells_z = 0
    constant_cols: List[str] = []
    id_like_cols: List[str] = []
    empty_cols: List[str] = []

    def add_issue(severity: str, itype: str, title: str, detail: str,
                  affected: str, count: int, recommendation: Optional[dict],
                  alt: Optional[dict] = None) -> None:
        entry = {
            "severity": severity, "type": itype, "title": title, "detail": detail,
            "columns": affected, "count": int(count), "recommendation": recommendation,
        }
        if alt:
            entry["alternative"] = alt
        issues.append(entry)

    for col in df.columns:
        s = df[col]
        role = roles.get(col, ROLE_TEXT)
        missing = int(s.isna().sum())
        missing_cells += missing
        nunique = int(s.nunique(dropna=True))
        entry = {
            "name": col,
            "role": role,
            "dtype": str(s.dtype),
            "missing": missing,
            "missing_pct": round(100 * missing / max(n_rows, 1), 2),
            "unique": nunique,
            "unique_pct": round(100 * nunique / max(n_rows, 1), 2),
            "memory_kb": round(float(s.memory_usage(deep=True)) / 1024, 1),
            "constant": bool(nunique <= 1 and missing < n_rows),
            "examples": [json_value(v) for v in s.dropna().head(3)],
        }
        if n_rows and s.isna().all():
            empty_cols.append(col)

        # ---- invalid values destroyed by type coercion ("1O50" in a number col) ----
        col_losses = (losses or {}).get(col) or []
        if col_losses:
            invalid_values_total += len(col_losses)
            entry["invalid_values"] = len(col_losses)
            samples = ", ".join(f"'{l['value']}'" for l in col_losses[:4])
            if role == ROLE_DATETIME:
                itype, headline = "invalid_dates", f"Invalid dates in '{col}'"
                why = ("do not fit this column's date format and are treated as blank "
                       "by charts and statistics")
            else:
                itype, headline = "invalid_values", f"Invalid values in '{col}'"
                why = (f"do not fit this column's type ('{role}') and are treated as "
                       "blank by charts and statistics")
            add_issue(
                "high", itype, headline,
                f"{len(col_losses)} value(s) ({samples}) {why}. They were "
                "flagged, not guessed: fix the raw values (e.g. '1O50' → 1050) or "
                "remove them explicitly. The original upload keeps the untouched "
                "values.",
                col, len(col_losses), None,
            )

        # ---- numeric stats, outliers & suspicious values ----
        if role == ROLE_NUMERIC and pd.api.types.is_numeric_dtype(s):
            clean = s.dropna()
            if not clean.empty:
                d = clean.describe()
                entry["stats"] = {
                    "mean": _round(d["mean"]), "median": _round(d["50%"]),
                    "std": _round(d["std"]), "min": _round(d["min"]),
                    "q25": _round(d["25%"]), "q75": _round(d["75%"]),
                    "max": _round(d["max"]),
                }
                lo, hi, n_iqr, mask_iqr = _numeric_outliers(s, "iqr", 1.5)
                _, _, n_z, _ = _numeric_outliers(s, "zscore", 3.0)
                entry["outliers"] = {"iqr": n_iqr, "zscore": n_z,
                                     "iqr_bounds": [_round(lo), _round(hi)]}
                outlier_cells_iqr += n_iqr
                outlier_cells_z += n_z
                if n_iqr:
                    sample = _sample(s, mask_iqr)
                    entry["outlier_values"] = sample
                    shown = ", ".join(str(v["value"]) for v in sample[:4])
                    add_issue(
                        "medium", "outliers",
                        f"Outliers in '{col}'",
                        f"{n_iqr} value(s) fall outside the IQR fence "
                        f"[{_round(lo)}, {_round(hi)}] (1.5 × IQR)"
                        + (f" — e.g. {shown}" if shown else "")
                        + ". They may be data-entry mistakes or genuine extremes: "
                        "verify each value before treating it. Nothing is changed "
                        "unless you approve a treatment below.",
                        col, n_iqr,
                        # SAFE default: only flag, never modify
                        {"type": "handle_outliers", "label": "Flag outliers in a new column (safe)",
                         "params": {"columns": [col], "method": "iqr", "threshold": 1.5,
                                    "action": "flag"}, "destructive": False},
                        # destructive alternatives — need explicit approval
                        {"type": "handle_outliers", "label": "Set outliers to missing (needs approval)",
                         "params": {"columns": [col], "method": "iqr", "threshold": 1.5,
                                    "action": "nullify"}, "destructive": True},
                    )
                sus = _suspicious_numeric_values(s, col)
                neg_vals = sus["negatives"]
                impl_vals = sus["implausible"]
                ext_vals = sus["extreme"]
                if neg_vals:
                    suspicious_total += len(neg_vals)
                    entry["negative_values"] = neg_vals
                    shown = ", ".join(f"{v['value']} (row {v['row']})" for v in neg_vals[:4])
                    add_issue(
                        "medium", "suspicious_values",
                        f"Negative values in '{col}'",
                        f"Negative value(s): {shown}. Counts, quantities and amounts are "
                        "usually not negative — verify whether these are sign/keying "
                        "mistakes. CleanFlow flags them and will not auto-correct.",
                        col, len(neg_vals), None,
                        {"type": "replace_invalid", "label": "Set negatives to missing (explicit rule)",
                         "params": {"columns": [col],
                                    "values": [v["value"] for v in neg_vals[:50]],
                                    "fill_value": None}, "destructive": False},
                    )
                if impl_vals:
                    suspicious_total += len(impl_vals)
                    entry["implausible_values"] = impl_vals
                    shown = ", ".join(str(v["value"]) for v in impl_vals[:4])
                    add_issue(
                        "medium", "suspicious_values",
                        f"Implausible values in '{col}'",
                        f"Value(s) {shown} fall outside the plausible range "
                        f"{sus['range']} suggested by the column name. Flagged for "
                        "review — CleanFlow will not invent corrections.",
                        col, len(impl_vals), None,
                        {"type": "replace_invalid", "label": "Set them to missing (explicit rule)",
                         "params": {"columns": [col],
                                    "values": [v["value"] for v in impl_vals[:50]],
                                    "fill_value": None}, "destructive": False},
                    )
                elif ext_vals:
                    suspicious_total += len(ext_vals)
                    entry["extreme_values"] = ext_vals
                    shown = ", ".join(str(v["value"]) for v in ext_vals[:4])
                    add_issue(
                        "low", "suspicious_values",
                        f"Extreme values in '{col}'",
                        f"Value(s) {shown} sit more than 5 standard deviations from the "
                        "mean. Often genuine — verify before any treatment.",
                        col, len(ext_vals), None,
                    )

        # ---- datetime: invalid + ambiguous dates ----
        if role == ROLE_DATETIME:
            entry["stats"] = {
                "min": str(s.min()) if s.notna().any() else None,
                "max": str(s.max()) if s.notna().any() else None,
            }
            n_amb, amb_examples = 0, []
            if not pd.api.types.is_datetime64_any_dtype(s):
                n_bad = _invalid_date_count(s)
                if n_bad:
                    invalid_date_total += n_bad
                    entry["invalid_dates"] = n_bad
                    bad_examples = _invalid_date_examples(s)
                    shown = ", ".join(f"'{b}'" for b in bad_examples[:3])
                    add_issue(
                        "medium", "invalid_dates",
                        f"Invalid dates in '{col}'",
                        f"{n_bad} value(s) ({shown}) look like dates but cannot be parsed. "
                        "Recommended fix parses the column and KEEPS the bad values "
                        "flagged in a separate column — they are only set to missing if "
                        "you explicitly choose that option.",
                        col, n_bad,
                        {"type": "parse_dates", "label": "Parse dates, flag bad values (safe)",
                         "params": {"columns": [col], "on_error": "flag"},
                         "destructive": False},
                        {"type": "parse_dates", "label": "Parse dates, set bad values to missing (needs approval)",
                         "params": {"columns": [col], "on_error": "missing"},
                         "destructive": True},
                    )
                n_amb, amb_examples = _ambiguous_dates(s)
            else:
                # the stored text was already coerced month-first at load time;
                # the raw-text ambiguity report (from the store) is the only way
                # to still ask the user which convention is correct
                info = (ambiguous or {}).get(col) or {}
                n_amb = int(info.get("count") or 0)
                amb_examples = list(info.get("examples") or [])
            if n_amb:
                ambiguous_total += n_amb
                entry["ambiguous_dates"] = n_amb
                shown = ", ".join(f"'{a}'" for a in amb_examples[:3])
                add_issue(
                    "medium", "ambiguous_dates",
                    f"Ambiguous dates in '{col}'",
                    f"{n_amb} value(s) ({shown}) could be read day-first or "
                    "month-first — for example 12-05-2024 may be 5 December or 12 "
                    "May. Nothing is interpreted until you confirm the convention.",
                    col, n_amb,
                    {"type": "parse_dates", "label": "Parse day-first (DD-MM-YYYY)",
                     "params": {"columns": [col], "dayfirst": True, "on_error": "flag"},
                     "destructive": False},
                    {"type": "parse_dates", "label": "Parse month-first (MM-DD-YYYY)",
                     "params": {"columns": [col], "dayfirst": False, "on_error": "flag"},
                     "destructive": False},
                )

        # ---- text quality ----
        if role in (ROLE_TEXT, ROLE_CATEGORICAL) and nunique > 0:
            text_cells += int(s.notna().sum())
            ti = _text_issues(s)
            whitespace_cells += ti["whitespace"]
            if ti["case_variants"]:
                case_variant_cols += 1
                examples = ti.get("variant_examples", [])[:2]
                add_issue(
                    "low", "inconsistent_text",
                    f"Inconsistent category casing in '{col}'",
                    f"{ti['case_variants']} value(s) differ only by letter case or spacing "
                    + (f'(e.g. "' + '" vs "'.join(examples) + '"). ' if examples else "")
                    + "Standardize them so charts group them correctly.",
                    col, ti["case_variants"],
                    {"type": "standardize_categories", "label": "Standardize categories",
                     "params": {"columns": [col]}, "destructive": False},
                )
            if ti["whitespace"]:
                add_issue(
                    "low", "whitespace",
                    f"Whitespace issues in '{col}'",
                    f"{ti['whitespace']} value(s) have leading/trailing or repeated spaces.",
                    col, ti["whitespace"],
                    {"type": "clean_text", "label": "Trim & collapse spaces",
                     "params": {"columns": [col], "trim": True, "collapse": True},
                     "destructive": False},
                )
            if ti["sentinels"]:
                add_issue(
                    "medium", "invalid_values",
                    f"Sentinel values in '{col}'",
                    f"Found placeholder value(s) {ti['sentinel_values']} that usually mean "
                    "'no data'. Convert them to proper missing values?",
                    col, ti["sentinels"],
                    {"type": "replace_invalid", "label": "Convert sentinels to missing",
                     "params": {"columns": [col], "values": ti["sentinel_values"],
                                "fill_value": None}, "destructive": False},
                )
            if nunique <= 8:
                vc = s.value_counts(dropna=True).head(8)
                entry["top_values"] = [{"value": json_value(v), "count": int(c)} for v, c in vc.items()]
            if role == ROLE_TEXT and _looks_numeric_text(s):
                numeric_text_cols.append(col)

        # ---- e-mail validation ----
        if role in (ROLE_TEXT, ROLE_CATEGORICAL):
            em = _email_issues(s, col)
            if em["is_email_col"] and em["count"]:
                invalid_email_total += em["count"]
                entry["invalid_emails"] = em["count"]
                shown = ", ".join(f"'{v['value']}'" for v in em["invalid"][:3])
                add_issue(
                    "medium", "invalid_emails",
                    f"Invalid e-mail addresses in '{col}'",
                    f"{em['count']} value(s) ({shown}) are not structurally valid e-mail "
                    "addresses (a valid address needs local@domain.tld — e.g. "
                    "kabir.khan@example is missing the domain ending). Flagged only; "
                    "CleanFlow never invents corrections.",
                    col, em["count"],
                    {"type": "validate_emails", "label": "Flag invalid e-mails in a new column (safe)",
                     "params": {"columns": [col], "action": "flag"}, "destructive": False},
                    {"type": "validate_emails", "label": "Set invalid e-mails to missing (needs approval)",
                     "params": {"columns": [col], "action": "missing"}, "destructive": True},
                )

        # ---- constant / high-cardinality ----
        if entry["constant"]:
            constant_cols.append(col)
        low_name = col.lower()
        name_suggests_id = (low_name == "id" or low_name.endswith("_id")
                            or low_name.endswith("id") and len(low_name) > 2
                            or low_name in ("code", "uuid", "guid", "key"))
        if n_rows >= 4 and name_suggests_id and nunique >= 0.9 * n_rows \
                and role != ROLE_NUMERIC:
            id_like_cols.append(col)
        elif n_rows > 20 and nunique >= 0.98 * n_rows and role != ROLE_NUMERIC:
            id_like_cols.append(col)

        # ---- wrong dtype: numbers stored as text ----
        if role in (ROLE_TEXT, ROLE_CATEGORICAL) and col in numeric_text_cols:
            add_issue(
                "high", "wrong_dtype",
                f"'{col}' looks numeric but is stored as text",
                f"Almost all values in '{col}' parse as numbers, yet the column is typed as "
                f"'{role}'. Charts and statistics will ignore it until it is converted.",
                col, int(s.notna().sum()),
                {"type": "convert_type", "label": "Convert to number",
                 "params": {"columns": [col], "target": "number"}, "destructive": False},
            )

        # ---- missing values issue (per column, aggregated later per severity) ----
        if missing > 0:
            severity = "high" if missing / max(n_rows, 1) > 0.4 else "medium"
            strategy = "mean" if role == ROLE_NUMERIC else "mode"
            add_issue(
                severity, "missing_values",
                f"Missing values in '{col}'",
                f"{missing} of {n_rows} row(s) ({entry['missing_pct']}%) have no value. "
                f"Recommended for {role} data: fill with {strategy}. Filling rewrites "
                "cells, so review the strategy before applying it.",
                col, missing,
                {"type": "fill_missing", "label": f"Fill with {strategy}",
                 "params": {"columns": [col], "strategy": strategy}, "destructive": False},
                {"type": "drop_missing", "label": "Drop incomplete rows",
                 "params": {"columns": [col], "how": "any"}, "destructive": True},
            )

        columns.append(entry)

    # ---- dataset-level issues ----
    if duplicate_rows:
        add_issue(
            "high", "duplicates", "Duplicate rows",
            f"{duplicate_rows} row(s) are exact duplicates of another row "
            f"({round(100 * duplicate_rows / max(n_rows, 1), 1)}% of the dataset).",
            "(whole table)", duplicate_rows,
            {"type": "drop_duplicates", "label": "Remove duplicate rows",
             "params": {"keep": "first"}, "destructive": True},
        )

    # key-based duplicates: identical everywhere except an identifier column
    key_cols = [c for c in df.columns if c not in id_like_cols]
    near_dup_rows = 0
    if id_like_cols and key_cols and n_rows > 1:
        key_dup = int(df.duplicated(subset=key_cols).sum())
        near = key_dup - duplicate_rows
        if near > 0:
            near_dup_rows = near
            example = _dup_example(df, key_cols, id_like_cols)
            add_issue(
                "high", "possible_duplicates",
                "Possible duplicate records (only the identifier differs)",
                f"{near} row(s) repeat the same information in every non-identifier column "
                f"({', '.join(key_cols[:6])}{'…' if len(key_cols) > 6 else ''}) but differ in "
                f"{', '.join(id_like_cols[:3])}. {example} Review and remove the true "
                "duplicates — matching on key columns is configurable.",
                ", ".join(id_like_cols[:3]), near,
                {"type": "drop_duplicates", "label": "Remove duplicates (match on non-ID columns)",
                 "params": {"columns": key_cols, "keep": "first"}, "destructive": True},
                {"type": "flag_duplicates", "label": "Flag duplicate groups (safe — removes nothing)",
                 "params": {"columns": key_cols, "method": "exact"}, "destructive": False},
            )

    # normalized near-duplicates: same record re-typed with different casing/spacing
    if not id_like_cols and key_cols and 1 < n_rows <= 20000:
        norm = df[key_cols].astype(str)
        for c in norm.columns:
            norm[c] = norm[c].str.strip().str.lower().str.replace(r"[^a-z0-9]", "", regex=True)
        nonblank = (norm != "").all(axis=1)
        if nonblank.any():
            norm_dup = int(norm[nonblank].duplicated().sum())
            raw_dup = int(df[nonblank].duplicated().sum())
            extra = norm_dup - raw_dup
            if extra > 0:
                near_dup_rows += extra
                add_issue(
                    "low", "possible_duplicates",
                    "Near-duplicate rows (differ by spacing/case/punctuation)",
                    f"{extra} row(s) become identical after normalizing letter case, "
                    "spaces and punctuation — probably the same record typed twice. "
                    "Standardize the text first, then remove duplicates if they are real.",
                    ", ".join(key_cols[:5]), extra,
                    {"type": "flag_duplicates", "label": "Flag normalized duplicate groups (safe)",
                     "params": {"columns": key_cols, "method": "normalized"},
                     "destructive": False},
                )

    empty_rows = int(df.isna().all(axis=1).sum()) if n_rows and n_cols else 0
    if empty_rows:
        add_issue(
            "low", "empty_rows", "Empty row(s)",
            f"{empty_rows} row(s) contain no values at all.",
            "(whole table)", empty_rows,
            {"type": "drop_missing", "label": "Remove empty rows",
             "params": {"columns": [], "how": "all"}, "destructive": True},
        )
    if empty_cols:
        add_issue(
            "low", "empty_columns", "Empty column(s)",
            f"{', '.join(empty_cols)} contain(s) no values in any row.",
            ", ".join(empty_cols), len(empty_cols),
            {"type": "drop_column", "label": "Remove empty column(s)",
             "params": {"columns": empty_cols}, "destructive": True},
        )
    if constant_cols:
        add_issue(
            "low", "constant_column", "Constant column(s)",
            f"{', '.join(constant_cols)} ha(s) the same value in every row and adds no "
            "information to analysis or charts.",
            ", ".join(constant_cols), len(constant_cols),
            {"type": "drop_constant_columns", "label": "Drop constant column(s)",
             "params": {}, "destructive": True},
        )
    for col in id_like_cols:
        add_issue(
            "low", "high_cardinality", f"'{col}' is ID-like (high cardinality)",
            f"Nearly every row has a distinct value in '{col}'. Keep it as an identifier, but "
            "exclude it from charts, encodings and correlation analysis.",
            col, int(df[col].nunique(dropna=True)), None,
        )

    # ---- quality score ----
    completeness = 1 - missing_cells / total_cells
    uniqueness = 1 - (duplicate_rows + near_dup_rows) / max(n_rows, 1)
    problem_cells = (invalid_date_total + outlier_cells_iqr + invalid_values_total
                     + invalid_email_total + suspicious_total)
    validity = 1 - problem_cells / max(total_cells * 0.05, n_rows, 1)
    validity = max(0.0, min(1.0, validity))
    consistency = 1 - (whitespace_cells + case_variant_cols * 2) / max(text_cells, 1)
    consistency = max(0.0, min(1.0, consistency))
    score = round(100 * sum(WEIGHTS[k] * v for k, v in
                            {"completeness": completeness, "uniqueness": uniqueness,
                             "validity": validity, "consistency": consistency}.items()))
    score = int(max(0, min(100, score)))

    severity_rank = {"high": 0, "medium": 1, "low": 2}
    issues.sort(key=lambda i: (severity_rank.get(i["severity"], 3), -i["count"]))

    return {
        "overview": {
            "rows": n_rows,
            "cols": n_cols,
            "memory_mb": memory_mb,
            "missing_cells": missing_cells,
            "duplicate_rows": duplicate_rows,
            "possible_duplicates": near_dup_rows,
            "invalid_values": invalid_values_total,
            "invalid_emails": invalid_email_total,
            "suspicious_values": suspicious_total,
            "ambiguous_dates": ambiguous_total,
            "empty_rows": empty_rows,
            "empty_columns": len(empty_cols),
            "outliers_iqr": outlier_cells_iqr,
            "outliers_zscore": outlier_cells_z,
            "quality_score": score,
            "grade": _grade(score),
        },
        "scores": {
            "completeness": round(completeness * 100),
            "uniqueness": round(uniqueness * 100),
            "validity": round(validity * 100),
            "consistency": round(consistency * 100),
        },
        "issues": issues,
        "columns": columns,
    }
