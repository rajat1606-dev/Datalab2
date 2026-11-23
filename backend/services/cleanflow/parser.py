"""CleanFlow file parsing — CSV, TSV, TXT, XLSX, XLSM, XLS and JSON.

Delegates CSV/Excel handling to the existing DataLab parser
(`services.dataframe.parse_upload`) and adds JSON / JSON Lines plus the legacy
.xls format on top, so CleanFlow accepts a superset of the original formats.
"""
from __future__ import annotations

import io
import json
from typing import List

import pandas as pd

from services.dataframe import DataError, _dedupe_names, parse_upload

MAX_UPLOAD_BYTES = 15 * 1024 * 1024  # 15 MB

OK_EXTENSIONS = (".csv", ".tsv", ".txt", ".xlsx", ".xlsm", ".xls", ".json", ".jsonl")


def _tidy(df: pd.DataFrame) -> pd.DataFrame:
    """Shared post-parse clean-up: dedupe headers, drop empty rows/cols."""
    df.columns = _dedupe_names([str(c) for c in df.columns.tolist()])
    keep = [c for c in df.columns if not str(c).lower().startswith("unnamed")]
    df = df[keep]
    for c in df.columns:
        if df[c].dtype == object:
            df[c] = df[c].replace({"": None})
    df = df.dropna(how="all").dropna(axis=1, how="all").reset_index(drop=True)
    if df.shape[0] == 0 or df.shape[1] == 0:
        raise DataError("The file does not contain any usable data.")
    return df


def _parse_json_text(text: str) -> pd.DataFrame:
    text = text.strip()
    if not text:
        raise DataError("The JSON file is empty.")

    # Standard JSON first; fall back to JSON Lines (one object per line).
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        records: List[dict] = []
        for i, line in enumerate(text.splitlines()):
            line = line.strip().rstrip(",")
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise DataError(f"Could not parse JSON on line {i + 1}: {exc}") from exc
            if not isinstance(obj, dict):
                raise DataError("JSON Lines entries must be objects like {\"col\": value}.")
            records.append(obj)
        if not records:
            raise DataError("No usable JSON records were found.")
        return _tidy(pd.json_normalize(records))

    if isinstance(payload, list):
        if not payload:
            raise DataError("The JSON array is empty.")
        if all(isinstance(x, dict) for x in payload):
            return _tidy(pd.json_normalize(payload))
        return _tidy(pd.DataFrame({"value": payload}))

    if isinstance(payload, dict):
        lists = [v for v in payload.values() if isinstance(v, list)]
        if payload and len(lists) == len(payload):
            # {"col": [..], "col2": [..]} — column-oriented
            lengths = {len(v) for v in payload.values()}
            if len(lengths) > 1:
                raise DataError("JSON columns must all have the same length.")
            return _tidy(pd.DataFrame(payload))
        if all(isinstance(v, (str, int, float, bool)) or v is None for v in payload.values()):
            return _tidy(pd.DataFrame([payload]))  # single record
        return _tidy(pd.json_normalize(payload))

    raise DataError("Unsupported JSON structure. Use an array of objects, "
                    "an object of columns, or JSON Lines.")


def parse_cleanflow_upload(filename: str, raw: bytes) -> pd.DataFrame:
    """Parse any CleanFlow-supported upload into a DataFrame."""
    lower = (filename or "").lower()
    if not lower:
        raise DataError("The uploaded file has no name.")

    if not lower.endswith(OK_EXTENSIONS):
        wanted = ", ".join(OK_EXTENSIONS)
        raise DataError(f"Unsupported file type. Please upload one of: {wanted}.")

    if len(raw) == 0:
        raise DataError("The uploaded file is empty.")

    if lower.endswith(".json") or lower.endswith(".jsonl"):
        text = None
        for enc in ("utf-8-sig", "utf-8", "latin-1"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            raise DataError("Could not decode the JSON file. Please save it as UTF-8.")
        return _parse_json_text(text)

    if lower.endswith(".xls"):
        try:
            df = pd.read_excel(io.BytesIO(raw), engine="xlrd")
        except Exception as exc:
            raise DataError(f"Could not read the .xls file: {exc}")
        return _tidy(df)

    # CSV / TSV / TXT / XLSX / XLSM — reuse the battle-tested DataLab parser.
    return parse_upload(filename, raw)
