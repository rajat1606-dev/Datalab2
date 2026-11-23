"""CleanFlow cleaning & transformation operations.

A single registry (`OPS`) drives everything: the API validation, the approval
rules and the dynamic forms rendered by the frontend (Transform page and ELT
Pipeline Builder fetch the registry via ``GET /api/cleanflow/ops``).

Design rules (from the CleanFlow spec):
  - operations never touch the original upload; callers work on a copy
  - destructive operations must arrive with ``approved: true``
  - suspicious values are flagged / set to missing, never silently "guessed"
  - every operation returns a human-readable log entry

`apply_ops(df, roles, operations, enforce_approval)` returns
``(new_df, new_roles, log_entries)``.
"""
from __future__ import annotations

import re
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from services.cleanflow.profiler import _numeric_outliers
from services.dataframe import (
    ROLE_CATEGORICAL,
    ROLE_DATETIME,
    ROLE_NUMERIC,
    ROLE_TEXT,
    DataError,
    json_value,
)

UNDO_LIMIT = 10  # undo snapshots kept per dataset

Op = dict

# A structurally valid e-mail address (local@domain.tld). Same rule as the
# profiler so detection and cleaning agree. Invalid addresses are flagged or
# nulled only on request — never "corrected" by guessing.
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$")

# Typo-level fuzzy duplicate matching is O(n²) — cap the number of unique keys.
FUZZY_MAX_KEYS = 800


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _require_columns(df: pd.DataFrame, cols: List[str], what: str = "operation") -> None:
    if not cols:
        raise DataError(f"Select at least one column for the '{what}' operation.")
    for c in cols:
        if c not in df.columns:
            raise DataError(f"Column '{c}' does not exist in this dataset.")


def _numeric_columns(df: pd.DataFrame, roles: Dict[str, str], cols: List[str]) -> List[str]:
    out = []
    for c in cols:
        if pd.api.types.is_numeric_dtype(df[c]):
            out.append(c)
        elif roles.get(c) == ROLE_NUMERIC:
            df[c] = pd.to_numeric(df[c].astype(str).str.replace(",", "", regex=False),
                                  errors="coerce")
            out.append(c)
        else:
            raise DataError(f"Column '{c}' must be numeric for this operation.")
    return out


def _log(op: str, label: str, detail: str, affected: int, columns=None) -> dict:
    return {"op": op, "label": label, "detail": detail,
            "affected": int(affected), "columns": columns or []}


# ---------------------------------------------------------------------------
# handlers:  fn(df, roles, op) -> (df, roles, log_entry)
# ---------------------------------------------------------------------------

def _h_fill_missing(df, roles, op):
    cols = list(op.get("columns") or [])
    _require_columns(df, cols, "fill missing values")
    strategy = op.get("strategy") or "mode"
    value = op.get("value")
    filled = 0
    for c in cols:
        s = df[c]
        before = int(s.isna().sum())
        if before == 0:
            continue
        if strategy in ("mean", "median"):
            _numeric_columns(df, roles, [c])
            s = df[c]
            if s.notna().sum() == 0:
                raise DataError(f"Column '{c}' has no numeric values to compute a fill value from.")
            df[c] = s.fillna(s.mean() if strategy == "mean" else s.median())
        elif strategy == "mode":
            modes = s.mode(dropna=True)
            if modes.empty:
                continue
            df[c] = s.fillna(modes.iloc[0])
        elif strategy == "ffill":
            df[c] = s.ffill()
        elif strategy == "bfill":
            df[c] = s.bfill()
        elif strategy == "constant":
            df[c] = s.fillna(value)
        else:
            raise DataError(f"Unknown fill strategy '{strategy}'.")
        filled += before - int(df[c].isna().sum())
    return df, roles, _log("fill_missing", "Fill missing values",
                           f"Filled {filled} missing cell(s) using '{strategy}'", filled, cols)


def _h_drop_missing(df, roles, op):
    cols = list(op.get("columns") or [])
    for c in cols:
        if c not in df.columns:
            raise DataError(f"Column '{c}' does not exist in this dataset.")
    before = len(df)
    df = df.dropna(subset=cols or None, how=op.get("how") or "any")
    removed = before - len(df)
    if df.empty and removed:
        raise DataError("That operation would remove every row, so it was rejected.")
    return df, roles, _log("drop_missing", "Drop incomplete rows",
                           f"Removed {removed} row(s) with missing values", removed, cols)


def _h_drop_duplicates(df, roles, op):
    cols = list(op.get("columns") or [])
    for c in cols:
        if c not in df.columns:
            raise DataError(f"Column '{c}' does not exist in this dataset.")
    if cols and len(cols) >= len(df.columns):
        raise DataError(
            "Duplicate matching must ignore at least one column — otherwise it is "
            "an exact whole-row match. Unselect the identifier column(s) you want "
            "to ignore, or run the operation without a column selection.")
    before = len(df)
    df = df.drop_duplicates(subset=cols or None, keep=op.get("keep") or "first")
    removed = before - len(df)
    return df, roles, _log("drop_duplicates", "Remove duplicates",
                           f"Removed {removed} duplicate row(s)" + (f" matching on {', '.join(cols)}" if cols else " (whole row)"),
                           removed, cols)


def _norm_key(s: pd.Series) -> pd.Series:
    """Normalized text key: lowercase, alphanumeric only (for near-duplicates)."""
    return (s.fillna("").astype(str).str.strip().str.lower()
             .str.replace(r"[^a-z0-9]", "", regex=True))


def _h_flag_duplicates(df, roles, op):
    """Mark suspected duplicate groups in a new column — removes nothing.

    method: exact (raw values) | normalized (case/space/punctuation-insensitive)
            | fuzzy (typo-level similarity, capped at 800 unique keys)
    Approximate methods only ADD a flag column; they never merge or delete rows.
    """
    cols = list(op.get("columns") or [])
    for c in cols:
        if c not in df.columns:
            raise DataError(f"Column '{c}' does not exist in this dataset.")
    method = op.get("method") or "normalized"
    if method not in ("exact", "normalized", "fuzzy"):
        raise DataError(f"Unknown duplicate method '{method}'.")
    threshold = op.get("similarity")
    try:
        threshold = float(threshold) if threshold is not None else 0.85
    except (TypeError, ValueError):
        threshold = 0.85
    if not 0.5 <= threshold <= 1.0:
        raise DataError("Similarity threshold must be between 0.5 and 1.0.")

    keys = df[cols] if cols else df
    if method == "normalized":
        keys = keys.apply(_norm_key, axis=0)
    joined = keys.astype(str).agg("\u241f".join, axis=1)  # ␟ unit-separator join

    if method == "fuzzy":
        uniq = pd.Series(joined.unique())
        if len(uniq) > FUZZY_MAX_KEYS:
            raise DataError(
                f"Fuzzy matching is limited to {FUZZY_MAX_KEYS} unique key "
                f"combinations (found {len(uniq)}). Use 'exact' or 'normalized' "
                "for larger datasets.")
        # union-find over pairwise similarities (real_quick_ratio pre-filter)
        parent = list(range(len(uniq)))

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        from difflib import SequenceMatcher
        lists = uniq.tolist()
        for i in range(len(lists)):
            for j in range(i + 1, len(lists)):
                sm = SequenceMatcher(None, lists[i], lists[j])
                if sm.real_quick_ratio() >= threshold and sm.ratio() >= threshold:
                    ri, rj = find(i), find(j)
                    if ri != rj:
                        parent[rj] = ri
        root_to_group: Dict[int, int] = {}
        group_of_key: Dict[str, int] = {}
        for k_i, key in enumerate(lists):
            root = find(k_i)
            if root not in root_to_group:
                root_to_group[root] = len(root_to_group) + 1
            group_of_key[key] = root_to_group[root]
        groups = joined.map(group_of_key)
    else:
        codes, _uniques = pd.factorize(joined)
        groups = pd.Series(codes + 1, index=df.index)  # 1-based group ids

    sizes = groups.map(groups.value_counts())
    dup_mask = sizes > 1
    flag_col = "duplicate_group"
    base = flag_col
    k = 2
    while base in df.columns:
        base = f"{flag_col}_{k}"
        k += 1
    df[base] = groups.where(dup_mask, None).astype("object")
    n_rows_flagged = int(dup_mask.sum())
    n_groups = int(groups[dup_mask].nunique())
    if n_rows_flagged == 0:
        detail = (f"No duplicate groups found (method={method}"
                  + (f", similarity≥{threshold}" if method == "fuzzy" else "") + ").")
        df = df.drop(columns=[base])
        return df, roles, _log("flag_duplicates", "Flag duplicates", detail, 0, cols)
    detail = (f"Flagged {n_rows_flagged} row(s) in {n_groups} duplicate group(s) "
              f"into '{base}' (method={method}" +
              (f", similarity≥{threshold}" if method == "fuzzy" else "") +
              "). Nothing was removed — review the groups before deduplicating.")
    return df, roles, _log("flag_duplicates", "Flag duplicates", detail,
                           n_rows_flagged, cols)


def _h_convert_type(df, roles, op):
    cols = list(op.get("columns") or [])
    _require_columns(df, cols, "convert type")
    target = op.get("target") or "text"
    date_format = op.get("date_format")
    dayfirst = bool(op.get("dayfirst", False))
    converted = 0
    for c in cols:
        s = df[c]
        if target == "number":
            if not pd.api.types.is_numeric_dtype(s):
                cleaned = s.astype(str).str.replace(",", "", regex=False).str.strip()
                num = pd.to_numeric(cleaned, errors="coerce")
                lost_mask = s.notna() & num.isna()
                lost = int(lost_mask.sum())
                if lost:
                    samples = ", ".join(f"'{v}'" for v in s[lost_mask].head(3))
                    raise DataError(
                        f"Column '{c}': {lost} value(s) cannot be parsed as numbers "
                        f"(e.g. {samples}). The operation was rejected and nothing was "
                        "changed — fix or remove those values first (see the flagged "
                        "invalid values in Data Profiling).")
                df[c] = num
            roles[c] = ROLE_NUMERIC
        elif target == "date":
            try:
                parsed = pd.to_datetime(s, errors="coerce", dayfirst=dayfirst,
                                        format=date_format if date_format else "mixed")
            except (ValueError, TypeError):
                parsed = pd.to_datetime(s.astype(str), errors="coerce",
                                        format="mixed", dayfirst=dayfirst)
            lost_mask = s.notna() & parsed.isna()
            lost = int(lost_mask.sum())
            if lost:
                samples = ", ".join(f"'{v}'" for v in s[lost_mask].head(3))
                raise DataError(
                    f"Column '{c}': {lost} value(s) cannot be parsed as dates"
                    + (f" with format '{date_format}'" if date_format else "")
                    + f" (e.g. {samples}). The operation was rejected and nothing was "
                    "changed — use 'Parse & format dates' which can keep bad values "
                    "flagged, or fix/remove them first.")
            df[c] = parsed
            roles[c] = ROLE_DATETIME
        elif target == "text":
            df[c] = s.astype(str).where(s.notna(), None)
            roles[c] = ROLE_TEXT
        elif target == "categorical":
            roles[c] = ROLE_CATEGORICAL
        else:
            raise DataError(f"Unknown target type '{target}'.")
        converted += 1
    return df, roles, _log("convert_type", "Convert column type",
                           f"Converted {converted} column(s) to '{target}'", converted, cols)


def _h_clean_text(df, roles, op):
    cols = list(op.get("columns") or [])
    _require_columns(df, cols, "clean text")
    trim = bool(op.get("trim", True))
    collapse = bool(op.get("collapse", True))
    case = op.get("case") or "none"
    touched = 0
    for c in cols:
        s = df[c]
        if pd.api.types.is_numeric_dtype(s) or pd.api.types.is_datetime64_any_dtype(s):
            continue
        strs = s.astype(str).where(s.notna(), None)
        changed = strs
        if trim:
            changed = changed.str.strip()
        if collapse:
            changed = changed.str.replace(r"\s+", " ", regex=True)
        if case == "lower":
            changed = changed.str.lower()
        elif case == "upper":
            changed = changed.str.upper()
        elif case == "title":
            changed = changed.str.title()
        new = changed.where(s.notna(), None)
        touched += int((new.fillna("§") != strs.fillna("§")).sum())
        df[c] = new
    return df, roles, _log("clean_text", "Clean text",
                           f"Standardized text in {len(cols)} column(s) "
                           f"(trim={trim}, collapse={collapse}, case={case})", touched, cols)


def _h_parse_dates(df, roles, op):
    """Parse date columns with explicit invalid-value handling.

    on_error="flag" (default, safe): valid values become datetimes, unparseable
    values KEEP their original text and are marked in a new
    '<column>_invalid_date' flag column. Nothing is lost or guessed.

    on_error="missing" (destructive, needs approval): unparseable values are
    set to missing.

    dayfirst: resolves ambiguous dates like 12-05-2024 (DD-MM vs MM-DD). The
    profiler detects ambiguity and asks the user to choose the convention.
    """
    cols = list(op.get("columns") or [])
    _require_columns(df, cols, "parse dates")
    date_format = op.get("date_format")
    unified = op.get("unified_format")
    dayfirst = bool(op.get("dayfirst", False))
    on_error = op.get("on_error") or "flag"
    if on_error not in ("flag", "missing"):
        raise DataError("Unknown invalid-date handling mode "
                        f"'{on_error}' (use 'flag' or 'missing').")
    parsed_total, flagged_total = 0, 0
    for c in cols:
        s = df[c]
        try:
            parsed = pd.to_datetime(s, errors="coerce", dayfirst=dayfirst,
                                    format=date_format if date_format else "mixed")
        except (ValueError, TypeError):
            parsed = pd.to_datetime(s.astype(str), errors="coerce",
                                    format="mixed", dayfirst=dayfirst)
        bad_mask = s.notna() & parsed.isna()
        failed = int(bad_mask.sum())
        flagged_total += failed
        if failed and on_error == "missing":
            # approved destructive path: bad values become missing
            if unified:
                df[c] = parsed.dt.strftime(unified).where(parsed.notna(), None)
                roles[c] = ROLE_TEXT
            else:
                df[c] = parsed
                roles[c] = ROLE_DATETIME
        elif failed and on_error == "flag":
            # safe path: keep the original text for bad values, flag them
            flag_col = f"{c}_invalid_date"
            base = flag_col
            k = 2
            while base in df.columns:
                base = f"{flag_col}_{k}"
                k += 1
            df[base] = bad_mask.astype(int)
            if unified:
                formatted = parsed.dt.strftime(unified)
                df[c] = formatted.where(~bad_mask, s).where(s.notna(), None)
                roles[c] = ROLE_TEXT
            else:
                # mixed column (datetimes + the kept bad text): store as text so
                # a reload cannot silently null the flagged values again
                df[c] = parsed.where(~bad_mask, s)
                roles[c] = ROLE_TEXT
        else:
            if unified:
                df[c] = parsed.dt.strftime(unified).where(parsed.notna(), None)
                roles[c] = ROLE_TEXT
            else:
                df[c] = parsed
                roles[c] = ROLE_DATETIME
        parsed_total += int(parsed.notna().sum())
    detail = (f"Parsed {parsed_total} date value(s) across {len(cols)} column(s)"
              + (" (day-first)" if dayfirst else ""))
    if flagged_total:
        if on_error == "flag":
            detail += (f"; {flagged_total} unparseable value(s) were KEPT and flagged "
                       "in '<column>_invalid_date' — nothing was lost")
        else:
            detail += f"; {flagged_total} unparseable value(s) were set to missing"
    return df, roles, _log("parse_dates", "Parse & format dates", detail,
                           parsed_total, cols)


def _h_handle_outliers(df, roles, op):
    cols = list(op.get("columns") or [])
    _require_columns(df, cols, "outlier handling")
    method = op.get("method") or "iqr"
    threshold = float(op.get("threshold") or (1.5 if method == "iqr" else 3.0))
    action = op.get("action") or "flag"
    if method not in ("iqr", "zscore"):
        raise DataError(f"Unknown outlier method '{method}'.")
    if action not in ("flag", "nullify", "remove"):
        raise DataError(f"Unknown outlier action '{action}'.")
    _numeric_columns(df, roles, cols)
    total = 0
    treated: List[str] = []
    if action == "flag":
        for c in cols:
            _, _, n, mask = _numeric_outliers(df[c], method, threshold)
            flag_col = f"{c}_outlier"
            df[flag_col] = mask.astype(int)
            total += n
            treated += _treated_samples(df[c], mask)
        detail = (f"Flagged {total} outlier value(s) ({method}, threshold={threshold}) "
                  "into flag column(s). No value was modified"
                  + (": " + ", ".join(treated[:6]) if treated else ""))
        return df, roles, _log("handle_outliers", "Outliers (flag)", detail, total, cols)
    if action == "nullify":
        for c in cols:
            _, _, n, mask = _numeric_outliers(df[c], method, threshold)
            treated += _treated_samples(df[c], mask)
            df.loc[mask, c] = np.nan
            total += n
        detail = (f"Set {total} outlier value(s) to missing ({method}, "
                  f"threshold={threshold})"
                  + (": " + ", ".join(treated[:6]) if treated else ""))
        return df, roles, _log("handle_outliers", "Outliers (nullify)", detail, total, cols)
    # remove
    before = len(df)
    mask_any = pd.Series(False, index=df.index)
    for c in cols:
        _, _, n, mask = _numeric_outliers(df[c], method, threshold)
        mask_any |= mask
        treated += _treated_samples(df[c], mask)
        total += n
    df = df.loc[~mask_any].reset_index(drop=True)
    removed = before - len(df)
    if df.empty:
        raise DataError("Removing those outliers would empty the dataset — rejected.")
    detail = (f"Removed {removed} row(s) containing {total} outlier value(s) "
              f"({method}, threshold={threshold})"
              + (": " + ", ".join(treated[:6]) if treated else ""))
    return df, roles, _log("handle_outliers", "Outliers (remove rows)", detail, removed, cols)


def _treated_samples(s: pd.Series, mask: pd.Series, limit: int = 6) -> List[str]:
    """"Value at row N" entries for the cells an operation touched."""
    hits = s[mask]
    return [f"{json_value(v)} (row {int(i) + 1})" for i, v in hits.head(limit).items()]


def _h_validate_emails(df, roles, op):
    """Structural e-mail validation: flag invalid addresses (safe) or set them
    to missing (destructive, approval required). Never invents corrections."""
    cols = list(op.get("columns") or [])
    _require_columns(df, cols, "e-mail validation")
    action = op.get("action") or "flag"
    if action not in ("flag", "missing"):
        raise DataError(f"Unknown e-mail action '{action}' (use 'flag' or 'missing').")
    total, flagged = 0, 0
    examples: List[str] = []
    for c in cols:
        s = df[c]
        if pd.api.types.is_numeric_dtype(s) or pd.api.types.is_datetime64_any_dtype(s):
            raise DataError(f"Column '{c}' is numeric/datetime — it cannot hold e-mail addresses.")
        strs = s.astype(str)
        non_empty = s.notna() & (strs.str.strip() != "")
        invalid = non_empty & ~strs.str.strip().map(lambda v: bool(EMAIL_RE.match(v)))
        n = int(invalid.sum())
        total += n
        examples += [f"{v} (row {int(i) + 1})" for i, v in s[invalid].head(4).items()]
        if n == 0:
            continue
        if action == "flag":
            flag_col = f"{c}_invalid_email"
            base = flag_col
            k = 2
            while base in df.columns:
                base = f"{flag_col}_{k}"
                k += 1
            df[base] = invalid.astype(int)
            flagged += n
        else:
            df.loc[invalid, c] = None
    label = "E-mail validation (flag)" if action == "flag" else "E-mail validation (nullify)"
    if total == 0:
        return df, roles, _log("validate_emails", label,
                               f"All e-mail addresses in {len(cols)} column(s) are valid", 0, cols)
    if action == "flag":
        detail = (f"Flagged {total} invalid e-mail(s) into flag column(s) — values kept "
                  "unchanged"
                  + (": " + ", ".join(examples[:4]) if examples else ""))
    else:
        detail = (f"Set {total} invalid e-mail(s) to missing"
                  + (": " + ", ".join(examples[:4]) if examples else ""))
    return df, roles, _log("validate_emails", label, detail, total, cols)


def _h_drop_constant(df, roles, op):
    const = [c for c in df.columns
             if df[c].nunique(dropna=True) <= 1 and not df[c].dropna().empty]
    if not const:
        return df, roles, _log("drop_constant_columns", "Drop constant columns",
                               "No constant columns found", 0)
    df = df.drop(columns=const)
    for c in const:
        roles.pop(c, None)
    return df, roles, _log("drop_constant_columns", "Drop constant columns",
                           f"Dropped constant column(s): {', '.join(const)}",
                           len(const), const)


def _h_drop_column(df, roles, op):
    cols = list(op.get("columns") or [])
    _require_columns(df, cols, "drop column")
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise DataError(f"Column(s) not found: {', '.join(missing)}")
    if len(cols) >= len(df.columns):
        raise DataError("Cannot drop every column of the dataset.")
    df = df.drop(columns=cols)
    for c in cols:
        roles.pop(c, None)
    return df, roles, _log("drop_column", "Drop columns",
                           f"Removed column(s): {', '.join(cols)}", len(cols), cols)


def _h_rename_column(df, roles, op):
    column = op.get("column")
    new_name = (op.get("new_name") or "").strip()
    if not column:
        raise DataError("Choose a column to rename.")
    if column not in df.columns:
        raise DataError(f"Column '{column}' does not exist in this dataset.")
    if not new_name:
        raise DataError("Enter a new column name.")
    if new_name == column:
        raise DataError("The new column name is the same as the current one.")
    if new_name in df.columns:
        raise DataError(f"A column named '{new_name}' already exists.")
    df = df.rename(columns={column: new_name})
    roles[new_name] = roles.pop(column, ROLE_TEXT)
    return df, roles, _log("rename_column", "Rename column",
                           f"Renamed '{column}' to '{new_name}'", 1, [column])


def _h_standardize_categories(df, roles, op):
    cols = list(op.get("columns") or [])
    _require_columns(df, cols, "standardize categories")
    changed = 0
    mapping_examples: List[str] = []
    for c in cols:
        s = df[c]
        if pd.api.types.is_numeric_dtype(s) or pd.api.types.is_datetime64_any_dtype(s):
            continue
        strs = s.astype(str).where(s.notna(), None)
        stripped = strs.str.strip()
        # most frequent original variant becomes the representative per case-fold group
        freq = stripped.value_counts(dropna=True)
        mapping: Dict[str, str] = {}
        for raw, n in freq.items():
            key = str(raw).strip().lower()
            if key not in mapping:
                mapping[key] = str(raw)
        new = stripped.str.strip().str.lower().map(mapping).where(s.notna(), None)
        col_changed = new.fillna("§") != strs.fillna("§")
        changed += int(col_changed.sum())
        if col_changed.any():
            pairs = [(strs[i], new[i]) for i in new.index[col_changed]][:3]
            mapping_examples += [f"'{a}' → '{b}'" for a, b in pairs if a != b]
        df[c] = new
    detail = (f"Unified casing/spacing in {len(cols)} column(s) "
              f"({changed} value(s) adjusted)"
              + (": " + ", ".join(mapping_examples[:4]) if mapping_examples else ""))
    return df, roles, _log("standardize_categories", "Standardize categories",
                           detail, changed, cols)


def _h_normalize(df, roles, op):
    cols = list(op.get("columns") or [])
    _require_columns(df, cols, "normalize")
    _numeric_columns(df, roles, cols)
    for c in cols:
        s = df[c]
        lo, hi = float(s.min()), float(s.max())
        if pd.isna(lo) or pd.isna(hi):
            continue
        if hi == lo:
            df[c] = 0.0
        else:
            df[c] = (s - lo) / (hi - lo)
    return df, roles, _log("normalize", "Normalize (0-1)",
                           f"Rescaled {len(cols)} column(s) to the 0-1 range", len(cols), cols)


def _h_standardize(df, roles, op):
    cols = list(op.get("columns") or [])
    _require_columns(df, cols, "standardize (z-score)")
    _numeric_columns(df, roles, cols)
    for c in cols:
        s = df[c]
        std = float(s.std())
        mean = float(s.mean())
        if pd.isna(std) or std == 0 or pd.isna(mean):
            continue
        df[c] = (s - mean) / std
    return df, roles, _log("standardize", "Standardize (z-score)",
                           f"Z-score standardized {len(cols)} column(s)", len(cols), cols)


def _h_label_encode(df, roles, op):
    cols = list(op.get("columns") or [])
    _require_columns(df, cols, "label encode")
    encoded = 0
    for c in cols:
        s = df[c]
        codes = s.astype("category").cat.codes  # -1 for missing
        df[c] = pd.Series(codes, index=df.index).astype("float").where(s.notna(), np.nan)
        roles[c] = ROLE_NUMERIC
        encoded += 1
    return df, roles, _log("label_encode", "Label encode",
                           f"Label-encoded {encoded} column(s) (missing → blank)", encoded, cols)


def _h_onehot_encode(df, roles, op):
    cols = list(op.get("columns") or [])
    _require_columns(df, cols, "one-hot encode")
    drop_first = bool(op.get("drop_first", False))
    created = 0
    for c in cols:
        dummies = pd.get_dummies(df[c].astype("object"), prefix=c, drop_first=drop_first,
                                 dummy_na=False)
        dummies = dummies.astype(int)
        created += len(dummies.columns)
        df = pd.concat([df.drop(columns=[c]), dummies], axis=1)
        roles.pop(c, None)
        for dc in dummies.columns:
            roles[dc] = ROLE_NUMERIC
    return df, roles, _log("onehot_encode", "One-hot encode",
                           f"One-hot encoded {len(cols)} column(s) into {created} indicator column(s)",
                           created, cols)


def _h_replace_invalid(df, roles, op):
    cols = list(op.get("columns") or [])
    _require_columns(df, cols, "invalid values")
    raw_values = list(op.get("values") or [])
    if not raw_values:
        raise DataError("Provide at least one invalid value to replace.")
    fill_value = op.get("fill_value")
    remove_rows = bool(op.get("remove_rows", False))
    text_vals = {str(v).strip().lower() for v in raw_values if isinstance(v, str)}
    num_vals = {v for v in raw_values if isinstance(v, (int, float)) and not isinstance(v, bool)}
    mask_any = pd.Series(False, index=df.index)
    for c in cols:
        s = df[c]
        mask = pd.Series(False, index=df.index)
        if pd.api.types.is_numeric_dtype(s) and num_vals:
            mask = s.isin(list(num_vals))
        if not pd.api.types.is_numeric_dtype(s) and text_vals:
            strs = s.astype(str).str.strip().str.lower()
            mask = mask | (strs.isin(text_vals) & s.notna())
        mask_any |= mask
        if not remove_rows:
            df.loc[mask, c] = np.nan if fill_value is None else fill_value
    affected = int(mask_any.sum())
    if remove_rows:
        if affected >= len(df):
            raise DataError("That operation would remove every row, so it was rejected.")
        df = df.loc[~mask_any].reset_index(drop=True)
        detail = (f"Removed {affected} row(s) containing invalid value(s) "
                  f"{raw_values[:4]}")
    else:
        target = "missing" if fill_value is None else f"'{fill_value}'"
        detail = f"Replaced {affected} invalid value(s) {raw_values[:4]} with {target}"
    return df, roles, _log("replace_invalid", "Invalid values", detail, affected, cols)


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------

def _destructive_outlier(op: Op) -> bool:
    return (op.get("action") or "flag") != "flag"


def _destructive_invalid(op: Op) -> bool:
    return bool(op.get("remove_rows", False))


def _destructive_parse_dates(op: Op) -> bool:
    """Nullifying unparseable dates rewrites data — flag mode (default) is safe."""
    return (op.get("on_error") or "flag") == "missing"


def _destructive_emails(op: Op) -> bool:
    return (op.get("action") or "flag") == "missing"


HANDLERS: Dict[str, Callable] = {
    "fill_missing": _h_fill_missing,
    "drop_missing": _h_drop_missing,
    "drop_duplicates": _h_drop_duplicates,
    "flag_duplicates": _h_flag_duplicates,
    "convert_type": _h_convert_type,
    "clean_text": _h_clean_text,
    "parse_dates": _h_parse_dates,
    "handle_outliers": _h_handle_outliers,
    "validate_emails": _h_validate_emails,
    "drop_constant_columns": _h_drop_constant,
    "drop_column": _h_drop_column,
    "rename_column": _h_rename_column,
    "standardize_categories": _h_standardize_categories,
    "normalize": _h_normalize,
    "standardize": _h_standardize,
    "label_encode": _h_label_encode,
    "onehot_encode": _h_onehot_encode,
    "replace_invalid": _h_replace_invalid,
}

# fields: type ∈ columns | column | select | text | number | bool
FIELDS: Dict[str, List[dict]] = {
    "fill_missing": [
        {"name": "columns", "type": "columns", "label": "Columns"},
        {"name": "strategy", "type": "select", "label": "Strategy",
         "options": ["mean", "median", "mode", "constant", "ffill", "bfill"], "default": "mode"},
        {"name": "value", "type": "text", "label": "Custom value (constant strategy)"},
    ],
    "drop_missing": [
        {"name": "columns", "type": "columns", "label": "Columns (empty = any column)"},
        {"name": "how", "type": "select", "label": "Drop row when",
         "options": ["any", "all"], "default": "any"},
    ],
    "drop_duplicates": [
        {"name": "columns", "type": "columns", "label": "Match on columns (empty = whole row; unselect ID columns to catch C001/C021-style duplicates)"},
        {"name": "keep", "type": "select", "label": "Keep",
         "options": ["first", "last"], "default": "first"},
    ],
    "flag_duplicates": [
        {"name": "columns", "type": "columns", "label": "Key columns (empty = all columns)"},
        {"name": "method", "type": "select", "label": "Match method",
         "options": ["exact", "normalized", "fuzzy"], "default": "normalized"},
        {"name": "similarity", "type": "number", "label": "Similarity threshold (fuzzy only, 0.5–1)"},
    ],
    "convert_type": [
        {"name": "columns", "type": "columns", "label": "Columns"},
        {"name": "target", "type": "select", "label": "New type",
         "options": ["number", "date", "text", "categorical"], "default": "number"},
        {"name": "date_format", "type": "text", "label": "Date format (optional, e.g. %d/%m/%Y)"},
        {"name": "dayfirst", "type": "bool", "label": "Parse dates day-first (DD/MM/YYYY)", "default": False},
    ],
    "clean_text": [
        {"name": "columns", "type": "columns", "label": "Columns"},
        {"name": "trim", "type": "bool", "label": "Trim spaces", "default": True},
        {"name": "collapse", "type": "bool", "label": "Collapse repeated spaces", "default": True},
        {"name": "case", "type": "select", "label": "Letter case",
         "options": ["none", "lower", "upper", "title"], "default": "none"},
    ],
    "parse_dates": [
        {"name": "columns", "type": "columns", "label": "Date columns"},
        {"name": "date_format", "type": "text", "label": "Input format (optional)"},
        {"name": "unified_format", "type": "text",
         "label": "Store as text in format (optional, e.g. %Y-%m-%d)"},
        {"name": "dayfirst", "type": "bool", "label": "Day-first (DD/MM/YYYY) for ambiguous dates", "default": False},
        {"name": "on_error", "type": "select", "label": "When a value is not a valid date",
         "options": ["flag", "missing"], "default": "flag"},
    ],
    "handle_outliers": [
        {"name": "columns", "type": "columns", "label": "Numeric columns"},
        {"name": "method", "type": "select", "label": "Method",
         "options": ["iqr", "zscore"], "default": "iqr"},
        {"name": "threshold", "type": "number", "label": "Threshold", "default": None},
        {"name": "action", "type": "select", "label": "Action",
         "options": ["flag", "nullify", "remove"], "default": "flag"},
    ],
    "validate_emails": [
        {"name": "columns", "type": "columns", "label": "E-mail columns"},
        {"name": "action", "type": "select", "label": "Action",
         "options": ["flag", "missing"], "default": "flag"},
    ],
    "drop_constant_columns": [],
    "drop_column": [{"name": "columns", "type": "columns", "label": "Columns to remove"}],
    "rename_column": [
        {"name": "column", "type": "column", "label": "Column"},
        {"name": "new_name", "type": "text", "label": "New name"},
    ],
    "standardize_categories": [{"name": "columns", "type": "columns", "label": "Columns"}],
    "normalize": [{"name": "columns", "type": "columns", "label": "Numeric columns"}],
    "standardize": [{"name": "columns", "type": "columns", "label": "Numeric columns"}],
    "label_encode": [{"name": "columns", "type": "columns", "label": "Category columns"}],
    "onehot_encode": [
        {"name": "columns", "type": "columns", "label": "Category columns"},
        {"name": "drop_first", "type": "bool", "label": "Drop first level", "default": False},
    ],
    "replace_invalid": [
        {"name": "columns", "type": "columns", "label": "Columns"},
        {"name": "values", "type": "text", "label": "Invalid values (comma separated)"},
        {"name": "fill_value", "type": "text", "label": "Replace with (empty = missing)"},
        {"name": "remove_rows", "type": "bool", "label": "Remove rows instead", "default": False},
    ],
}

OP_META = {
    "fill_missing":        {"label": "Fill missing values",      "group": "Clean",  "destructive": False},
    "drop_missing":        {"label": "Drop incomplete rows",     "group": "Clean",  "destructive": True},
    "drop_duplicates":     {"label": "Remove duplicate rows",    "group": "Clean",  "destructive": True},
    "flag_duplicates":     {"label": "Flag duplicate groups",    "group": "Clean",  "destructive": False},
    "convert_type":        {"label": "Convert column type",      "group": "Clean",  "destructive": False},
    "clean_text":          {"label": "Clean text",               "group": "Clean",  "destructive": False},
    "parse_dates":         {"label": "Parse & format dates",     "group": "Clean",  "destructive": _destructive_parse_dates},
    "handle_outliers":     {"label": "Handle outliers",          "group": "Clean",  "destructive": _destructive_outlier},
    "validate_emails":     {"label": "Validate e-mail addresses", "group": "Clean", "destructive": _destructive_emails},
    "drop_constant_columns": {"label": "Drop constant columns",  "group": "Clean",  "destructive": True},
    "drop_column":         {"label": "Drop columns",             "group": "Transform", "destructive": True},
    "rename_column":       {"label": "Rename column",            "group": "Transform", "destructive": False},
    "standardize_categories": {"label": "Standardize categories", "group": "Transform", "destructive": False},
    "normalize":           {"label": "Normalize (0-1)",          "group": "Transform", "destructive": False},
    "standardize":         {"label": "Standardize (z-score)",    "group": "Transform", "destructive": False},
    "label_encode":        {"label": "Label encode",             "group": "Transform", "destructive": False},
    "onehot_encode":       {"label": "One-hot encode",           "group": "Transform", "destructive": True},
    "replace_invalid":     {"label": "Invalid values",           "group": "Clean",  "destructive": _destructive_invalid},
}


def is_destructive(op: Op) -> bool:
    meta = OP_META.get(op.get("type"))
    if not meta:
        return False
    flag = meta["destructive"]
    return flag(op) if callable(flag) else bool(flag)


def ops_catalog() -> List[dict]:
    """Machine-readable registry for the frontend (Transform / Pipeline UIs)."""
    out = []
    for op_type, meta in OP_META.items():
        flag = meta["destructive"]
        # callable flags take the op; report the "worst case" for catalog purposes
        destructive = flag({"type": op_type, "action": "remove", "remove_rows": True}) \
            if callable(flag) else bool(flag)
        out.append({
            "type": op_type,
            "label": meta["label"],
            "group": meta["group"],
            "destructive": destructive,
            "fields": FIELDS[op_type],
        })
    return out


def _normalize_op(op: Op) -> Op:
    """Accept tolerant input: 'values'/'fill_value' as text lists, numbers as text."""
    op = dict(op)
    if isinstance(op.get("values"), str):
        op["values"] = [v.strip() for v in op["values"].split(",") if v.strip() != ""]
    vals = []
    for v in op.get("values") or []:
        if isinstance(v, str):
            s = v.strip()
            try:
                f = float(s)
                vals.append(int(f) if f.is_integer() and "." not in s and "e" not in s.lower() else f)
            except ValueError:
                vals.append(s)
        else:
            vals.append(v)
    op["values"] = vals
    if isinstance(op.get("threshold"), str):
        try:
            op["threshold"] = float(op["threshold"])
        except ValueError:
            op["threshold"] = None
    return op


def apply_ops(df: pd.DataFrame, roles: Dict[str, str], operations: List[Op],
              enforce_approval: bool = True) -> Tuple[pd.DataFrame, Dict[str, str], List[dict]]:
    """Apply a sequence of registry operations, with approval enforcement."""
    if df.empty:
        raise DataError("This dataset has no rows to process.")
    out = df.copy()
    out_roles = dict(roles)
    logs: List[dict] = []
    for raw in operations:
        op = _normalize_op(raw)
        op_type = op.get("type")
        meta = OP_META.get(op_type)
        if not meta or op_type not in HANDLERS:
            raise DataError(f"Unknown operation '{op_type}'.")
        if enforce_approval and is_destructive(op) and not op.get("approved"):
            raise DataError(
                f"The operation '{meta['label']}' removes or rewrites data, so it needs your "
                "explicit approval (set approved=true for this operation).")
        out, out_roles, entry = HANDLERS[op_type](out, out_roles, op)
        entry["destructive"] = is_destructive(op)
        logs.append(entry)
    return out, out_roles, logs
