"""Core pandas utilities.

This module handles:
  - parsing uploaded CSV/XLSX files into DataFrames
  - column "roles" (numeric / categorical / datetime / text) and type coercion
  - converting DataFrame cells into JSON-safe values
  - building DataFrames from manually entered data
"""
from __future__ import annotations

import io
import math
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

ROLE_NUMERIC = "numeric"
ROLE_CATEGORICAL = "categorical"
ROLE_DATETIME = "datetime"
ROLE_TEXT = "text"
VALID_ROLES = (ROLE_NUMERIC, ROLE_CATEGORICAL, ROLE_DATETIME, ROLE_TEXT)

MAX_UPLOAD_BYTES = 15 * 1024 * 1024  # 15 MB


class DataError(ValueError):
    """A user-facing data problem (routers convert this to HTTP 400)."""


# ---------------------------------------------------------------------------
# JSON-safe serialization
# ---------------------------------------------------------------------------

def json_value(v: Any) -> Any:
    """Convert one pandas/numpy cell into something JSON can serialize."""
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.floating):
        return round(float(v), 6)
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    if isinstance(v, (pd.Timestamp, np.datetime64)):
        return str(v)
    if isinstance(v, bytes):
        return v.decode("utf-8", "ignore")
    if isinstance(v, float):
        return round(v, 6)
    if isinstance(v, (int, str)):
        return v
    return str(v)


def dataframe_rows(df: pd.DataFrame, limit: Optional[int] = None, offset: int = 0) -> List[list]:
    """DataFrame -> list of row lists (JSON-safe)."""
    sub = df.iloc[offset: offset + limit] if limit is not None else df
    return [[json_value(v) for v in row] for row in sub.itertuples(index=False, name=None)]


# Characters that openpyxl refuses to write into .xlsx worksheets (control
# characters that are illegal in XML). Exporting without sanitizing them makes
# the Excel download fail with IllegalCharacterError.
_ILLEGAL_XLSX_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]")


def sanitize_for_excel(df: pd.DataFrame) -> pd.DataFrame:
    """Strip characters that are illegal inside .xlsx cells (no data loss
    beyond invisible control characters, which Excel cannot store anyway)."""
    out = df.copy()
    for c in out.columns:
        if pd.api.types.is_object_dtype(out[c]) or pd.api.types.is_string_dtype(out[c]):
            out[c] = out[c].map(
                lambda v: _ILLEGAL_XLSX_RE.sub("", v) if isinstance(v, str) else v)
    return out


# 12-05-2024 / 12.05.24 — day and month could be swapped (both ≤ 12).
_AMBIGUOUS_DATE_RE = re.compile(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})$")


def ambiguous_dates(s: pd.Series) -> tuple:
    """Count date-like strings where day/month could be swapped, with examples.

    "12-05-2024" is ambiguous (5 Dec or 12 May); "15/02/2024" is not (15 can
    only be a day). Returns (count, examples). Must run on the RAW text column
    — once pandas coerces it to datetime64 the ambiguity is already resolved
    (month-first) and undetectable.
    """
    try:
        vals = s.dropna().astype(str).str.strip()
    except Exception:
        return 0, []
    vals = vals[vals.str.match(_AMBIGUOUS_DATE_RE)]
    if vals.empty:
        return 0, []
    count, examples = 0, []
    for v in vals:
        m = _AMBIGUOUS_DATE_RE.match(v)
        if not m:
            continue
        a, b = int(m.group(1)), int(m.group(2))
        if a != b and a <= 12 and b <= 12:
            count += 1
            if len(examples) < 3:
                examples.append(str(v))
    return count, examples


def coercion_losses(s: pd.Series, role: Optional[str]) -> List[dict]:
    """Values that would be silently destroyed (set to NaN/NaT) by applying a
    column role — e.g. the numeric string '1O50' in a numeric column.

    CleanFlow uses this to *flag* invalid entries instead of quietly nulling
    them. Returns a list of {"row": index, "value": original} entries.
    """
    if role not in (ROLE_NUMERIC, ROLE_DATETIME):
        return []
    if not (pd.api.types.is_object_dtype(s) or pd.api.types.is_string_dtype(s)):
        return []
    vals = s.dropna()
    vals = vals[vals.astype(str).str.strip() != ""]
    if vals.empty:
        return []
    strs = vals.astype(str).str.strip()
    if role == ROLE_NUMERIC:
        parsed = pd.to_numeric(strs.str.replace(",", "", regex=False), errors="coerce")
    else:
        try:
            parsed = pd.to_datetime(strs, errors="coerce", format="mixed")
        except (ValueError, TypeError):
            return [{"row": int(i), "value": json_value(v)} for i, v in vals.items()]
    bad_idx = parsed.index[parsed.isna()]
    return [{"row": int(i), "value": json_value(vals.loc[i])} for i in bad_idx]


# ---------------------------------------------------------------------------
# Column roles
# ---------------------------------------------------------------------------

def _looks_numeric(s: pd.Series) -> bool:
    vals = s.dropna().astype(str).str.replace(",", "", regex=False).str.strip()
    if vals.empty:
        return False
    parsed = pd.to_numeric(vals, errors="coerce")
    return parsed.notna().mean() >= 0.9


def _looks_datetime(s: pd.Series) -> bool:
    vals = s.dropna().astype(str)
    # require a separator so plain numbers are never treated as dates
    vals = vals[vals.str.contains(r"[-/:]", regex=True)]
    if vals.empty:
        return False
    sample = vals.head(200)
    try:
        parsed = pd.to_datetime(sample, errors="coerce", format="mixed")
    except Exception:
        return False
    return parsed.notna().mean() >= 0.8


def infer_roles(df: pd.DataFrame) -> Dict[str, str]:
    """Guess the best-fitting role for every column."""
    roles: Dict[str, str] = {}
    n_rows = max(len(df), 1)
    for col in df.columns:
        s = df[col]
        if pd.api.types.is_bool_dtype(s):
            roles[col] = ROLE_CATEGORICAL
        elif pd.api.types.is_numeric_dtype(s):
            roles[col] = ROLE_NUMERIC
        elif pd.api.types.is_datetime64_any_dtype(s):
            roles[col] = ROLE_DATETIME
        else:
            if s.dropna().empty:
                roles[col] = ROLE_TEXT
            elif _looks_datetime(s):
                roles[col] = ROLE_DATETIME
            elif _looks_numeric(s):
                roles[col] = ROLE_NUMERIC
            else:
                nunique = int(s.nunique(dropna=True))
                if nunique <= 25 or nunique <= 0.1 * n_rows:
                    roles[col] = ROLE_CATEGORICAL
                else:
                    roles[col] = ROLE_TEXT
    return roles


def apply_roles(df: pd.DataFrame, roles: Optional[Dict[str, str]]) -> pd.DataFrame:
    """Coerce every column to its stored role (used when loading from SQLite)."""
    roles = roles or {}
    for col in df.columns:
        role = roles.get(col)
        if role not in VALID_ROLES:
            role = infer_roles(df[[col]])[col]
        s = df[col]
        try:
            if role == ROLE_NUMERIC and not pd.api.types.is_numeric_dtype(s):
                cleaned = s.astype(str).str.replace(",", "", regex=False).str.strip()
                df[col] = pd.to_numeric(cleaned, errors="coerce")
            elif role == ROLE_DATETIME and not pd.api.types.is_datetime64_any_dtype(s):
                df[col] = pd.to_datetime(s, errors="coerce", format="mixed")
            elif role in (ROLE_CATEGORICAL, ROLE_TEXT) and not (
                pd.api.types.is_object_dtype(s) or pd.api.types.is_string_dtype(s)
            ):
                df[col] = s.astype(str).where(s.notna(), None)
        except Exception:
            continue
    return df


def column_meta(df: pd.DataFrame, roles: Dict[str, str], n_examples: int = 3) -> List[dict]:
    """Per-column summary used by preview / dashboard pages."""
    meta = []
    for col in df.columns:
        s = df[col]
        examples = [json_value(v) for v in s.dropna().head(n_examples)]
        meta.append(
            {
                "name": col,
                "role": roles.get(col, ROLE_TEXT),
                "dtype": str(s.dtype),
                "missing": int(s.isna().sum()),
                "unique": int(s.nunique(dropna=True)),
                "examples": examples,
            }
        )
    return meta


# ---------------------------------------------------------------------------
# Uploads
# ---------------------------------------------------------------------------

def _dedupe_names(names: Sequence[Any]) -> List[str]:
    seen: dict = {}
    out: List[str] = []
    for raw in names:
        name = re.sub(r"\s+", " ", str(raw).strip()) or "column"
        base, k = name, 2
        while name.lower() in seen:
            name = f"{base}_{k}"
            k += 1
        seen[name.lower()] = True
        out.append(name)
    return out


def parse_upload(filename: str, raw: bytes) -> pd.DataFrame:
    """Read an uploaded CSV/XLSX file into a cleaned-up DataFrame."""
    lower = (filename or "").lower()
    if lower.endswith((".xlsx", ".xlsm")):
        try:
            df = pd.read_excel(io.BytesIO(raw), engine="openpyxl")
        except Exception as exc:
            raise DataError(f"Could not read the Excel file: {exc}")
    elif lower.endswith((".csv", ".txt", ".tsv")):
        text = None
        for enc in ("utf-8-sig", "utf-8", "latin-1"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            raise DataError("Could not decode the file. Please save it as UTF-8 CSV.")
        # Binary control characters corrupt the separator sniffer (it can pick
        # \x00 as the delimiter!) and are illegal in Excel anyway — strip them.
        text = _ILLEGAL_XLSX_RE.sub("", text)
        sep = "\t" if lower.endswith(".tsv") else None  # None -> sniff the separator
        if sep is None:
            # Sniff the delimiter ourselves, restricted to a whitelist — the
            # unrestricted sniffer can pick absurd delimiters (a letter such
            # as "l", or a binary control char) and shred the table.
            import csv as _csv
            try:
                sep = _csv.Sniffer().sniff(text[:8192], delimiters=",;\t|:").delimiter
            except _csv.Error:
                sep = ","
        try:
            df = pd.read_csv(io.StringIO(text), sep=sep, engine="python")
        except Exception as exc:
            raise DataError(f"Could not parse the CSV file: {exc}")
        # Single-column CSVs confuse the automatic separator sniffer (it
        # invents empty "Unnamed" columns). Re-read with plain commas when
        # the sniffed result has no usable header row.
        if df.empty or all(str(c).lower().startswith("unnamed") for c in df.columns):
            try:
                df = pd.read_csv(io.StringIO(text), sep=",", engine="python")
            except Exception:
                pass  # keep the sniffed frame and let downstream checks decide
    else:
        raise DataError("Unsupported file type. Please upload a .csv or .xlsx file.")

    df.columns = _dedupe_names(df.columns.tolist())
    keep = [c for c in df.columns if not c.lower().startswith("unnamed")]
    df = df[keep]
    for c in df.columns:
        if df[c].dtype == object:
            df[c] = df[c].replace({"": None})
    df = df.dropna(how="all").dropna(axis=1, how="all").reset_index(drop=True)
    if df.shape[0] == 0 or df.shape[1] == 0:
        raise DataError("The file does not contain any usable data.")
    return df


# ---------------------------------------------------------------------------
# Manual data entry
# ---------------------------------------------------------------------------

def build_manual_df(colspecs: Sequence[dict], rows: Sequence[Sequence[Any]]) -> Tuple[pd.DataFrame, List[str]]:
    """Build a DataFrame from manually entered columns + rows, coercing types.

    Returns (dataframe, warnings) where warnings describe values that could not
    be converted and were cleared.
    """
    names = [str(c["name"]).strip() for c in colspecs]
    types = [c.get("type", ROLE_TEXT) for c in colspecs]
    if any(not n for n in names):
        raise DataError("Column names cannot be empty.")
    lowered = [n.lower() for n in names]
    if len(set(lowered)) != len(lowered):
        raise DataError("Column names must be unique.")

    df = pd.DataFrame(list(rows), columns=names, dtype=object)
    warnings: List[str] = []
    for name, t in zip(names, types):
        s = df[name].replace({"": None, " ": None})
        if t == "number":
            raw = s.astype(str).str.replace(",", "", regex=False).str.strip()
            num = pd.to_numeric(raw, errors="coerce")
            lost = int((s.notna() & num.isna()).sum())
            if lost:
                warnings.append(f"{name}: {lost} value(s) were not valid numbers and were cleared.")
            df[name] = num
        elif t == "date":
            try:
                parsed = pd.to_datetime(s, errors="coerce", format="mixed")
            except Exception:
                parsed = pd.to_datetime(s.astype(str), errors="coerce", format="mixed")
            lost = int((s.notna() & parsed.isna()).sum())
            if lost:
                warnings.append(f"{name}: {lost} value(s) were not valid dates and were cleared.")
            df[name] = parsed
        else:
            df[name] = s
    return df, warnings
