"""CleanFlow data-quality report: before vs after, with download builders.

The "before" snapshot is the dataset's immutable original upload
(``original_data``); the "after" snapshot is the current working copy. The
report combines both profiles with the recorded CleanFlow operation log.
"""
from __future__ import annotations

import io
import json
from typing import Dict, List

import numpy as np
import pandas as pd

from services.cleanflow.profiler import profile_dataframe
from services.dataframe import apply_roles, json_value
from services.store import load_dataframe, load_frame_with_losses


def build_report(row: dict) -> dict:
    current, roles = load_dataframe(row)
    text = (row.get("original_data") or "").strip()
    if text:
        # profile the ORIGINAL with the same loss/ambiguity awareness so the
        # "before" view does not silently hide bad or ambiguous values
        df, orig_roles, losses, amb = load_frame_with_losses(
            text, row.get("original_roles") or "{}")
        original = df
        before = profile_dataframe(original, orig_roles, losses, amb)
    else:
        before = profile_dataframe(current, roles)

    after = profile_dataframe(current, roles)
    ov_b, ov_a = before["overview"], after["overview"]

    missing_handled = max(ov_b["missing_cells"] - ov_a["missing_cells"], 0)
    dups_removed = max(ov_b["duplicate_rows"] - ov_a["duplicate_rows"], 0)
    outliers_before = ov_b.get("outliers_iqr", 0)

    return {
        "dataset": {
            "id": row["id"], "name": row["name"],
            "created_at": row.get("created_at"), "updated_at": row.get("updated_at"),
        },
        "before": before,
        "after": after,
        "deltas": {
            "quality_score": ov_a["quality_score"] - ov_b["quality_score"],
            "missing_handled": missing_handled,
            "duplicates_removed": dups_removed,
            "rows_removed": max(ov_b["rows"] - ov_a["rows"], 0),
            "columns_added": max(ov_a["cols"] - ov_b["cols"], 0),
            "columns_removed": max(ov_b["cols"] - ov_a["cols"], 0),
            "outliers_detected": outliers_before,
        },
    }


def _cell(v) -> str:
    v = json_value(v)
    return "null" if v is None else str(v)


def preview_changes(df_before: pd.DataFrame, df_after: pd.DataFrame,
                    max_cells: int = 60) -> dict:
    """Cell-level before/after diff for one cleaning batch.

    Returns modified cells (row, column, old, new), how many rows were
    removed/added and which columns were added/removed/retyped. When rows were
    removed, cell-level comparison would misalign, so it reports the row
    counts instead — honest numbers over misleading diffs.
    """
    out = {
        "cells_changed": 0, "modified_cells": [],
        "rows_removed": max(len(df_before) - len(df_after), 0),
        "rows_added": max(len(df_after) - len(df_before), 0),
        "columns_added": [c for c in df_after.columns if c not in df_before.columns],
        "columns_removed": [c for c in df_before.columns if c not in df_after.columns],
        "columns_retyped": [],
    }
    if len(df_before) != len(df_after):
        out["note"] = ("Rows were removed or added in this batch, so no cell-level "
                       "diff is shown — use the operation log above for details.")
        return out
    common = [c for c in df_before.columns if c in df_after.columns]
    changed = pd.Series(False, index=df_before.index)
    for c in common:
        a, b = df_before[c], df_after[c]
        a_num = pd.api.types.is_numeric_dtype(a)
        b_num = pd.api.types.is_numeric_dtype(b)
        a_dt = pd.api.types.is_datetime64_any_dtype(a)
        b_dt = pd.api.types.is_datetime64_any_dtype(b)
        if (a_num != b_num) or (a_dt != b_dt):
            # column was retyped — every cell "looks" different; summarize only
            out["columns_retyped"].append(c)
            continue
        try:
            if a_num and b_num:
                fa = a.astype("float64")
                fb = b.astype("float64")
                diff_nan = fa.isna() ^ fb.isna()
                same = (fa.isna() & fb.isna()) | \
                    (~diff_nan & np.isclose(fa.fillna(0), fb.fillna(0),
                                            rtol=1e-9, atol=1e-12))
            elif a_dt and b_dt:
                same = (a.isna() & b.isna()) | (a == b)
            else:
                same = (a.isna() & b.isna()) | (
                    a.fillna("§").astype(str) == b.fillna("§").astype(str))
        except Exception:
            continue
        col_changed = ~same
        changed |= col_changed
        for i in df_before.index[col_changed]:
            if len(out["modified_cells"]) >= max_cells:
                break
            out["modified_cells"].append({
                "row": int(i) + 1, "column": c,
                "before": _cell(df_before.at[i, c]),
                "after": _cell(df_after.at[i, c]),
            })
    out["cells_changed"] = int(changed.sum())
    return out


def operations_timeline(log_rows: List[dict]) -> List[dict]:
    """Flatten cleanflow_log rows into an operation timeline for the report."""
    timeline: List[dict] = []
    for r in log_rows:
        try:
            ops = json.loads(r.get("ops") or "[]")
        except json.JSONDecodeError:
            ops = []
        timeline.append({
            "time": r.get("created_at"),
            "action": r.get("action"),
            "summary": r.get("summary"),
            "score_before": r.get("score_before"),
            "score_after": r.get("score_after"),
            "rows_before": r.get("rows_before"),
            "rows_after": r.get("rows_after"),
            "operations": [
                {"op": o.get("op"), "detail": o.get("detail"), "affected": o.get("affected"),
                 "destructive": o.get("destructive", False)}
                for o in ops if isinstance(o, dict)
            ],
        })
    return timeline


# ---------------------------------------------------------------------------
# Downloads
# ---------------------------------------------------------------------------

def report_to_json_bytes(report: dict, timeline: List[dict]) -> bytes:
    payload = {**report, "operations": timeline}
    return json.dumps(payload, indent=2, default=str).encode("utf-8")


def _esc(v) -> str:
    return (str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def report_to_html_bytes(report: dict, timeline: List[dict]) -> bytes:
    """A standalone printable HTML quality report (no external assets/paths)."""
    name = _esc(report["dataset"].get("name", "Dataset"))
    ov_b, ov_a = report["before"]["overview"], report["after"]["overview"]
    dl = report["deltas"]
    score_color = "#15803d" if ov_a["quality_score"] >= 75 else \
                  "#b45309" if ov_a["quality_score"] >= 50 else "#b91c1c"

    def metric_row(label, before, after, delta=None, suffix=""):
        delta_html = ""
        if delta is not None and delta != 0:
            good = delta > 0 if label in ("Quality score", "Columns") else delta < 0
            color = "#15803d" if good else "#b91c1c"
            sign = "+" if delta > 0 else ""
            delta_html = f'<td style="color:{color};font-weight:600">{sign}{delta}{suffix}</td>'
        elif delta is not None:
            delta_html = '<td style="color:#6b7280">—</td>'
        return (f"<tr><td>{_esc(label)}</td><td>{_esc(before)}{suffix}</td>"
                f"<td><b>{_esc(after)}{suffix}</b></td>{delta_html}</tr>")

    ops_rows = "".join(
        f"<tr><td>{_esc(t['time'])}</td><td>{_esc(t['action'])}</td>"
        f"<td>{_esc(t['summary'] or '')}</td>"
        f"<td>{_esc(t['score_before'])} → {_esc(t['score_after'])}</td></tr>"
        for t in timeline
    ) or '<tr><td colspan="4">No cleaning operations recorded yet.</td></tr>'

    cols_rows = "".join(
        f"<tr><td>{_esc(c['name'])}</td><td>{_esc(c['role'])}</td>"
        f"<td>{c['missing']} ({c['missing_pct']}%)</td><td>{c['unique']}</td>"
        f"<td>{c.get('outliers', {}).get('iqr', 0) if c.get('outliers') else 0}</td></tr>"
        for c in report["after"]["columns"]
    ) or '<tr><td colspan="5">No columns.</td></tr>'

    issues_rows = "".join(
        f"<tr><td><span style='color:{'#b91c1c' if i['severity'] == 'high' else '#b45309' if i['severity'] == 'medium' else '#6b7280'}'>"
        f"{_esc(i['severity'].upper())}</span></td><td>{_esc(i['title'])}</td>"
        f"<td>{_esc(i['detail'])}</td></tr>"
        for i in report["after"]["issues"]
    ) or '<tr><td colspan="3">No remaining issues detected. 🎉</td></tr>'

    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DataLab CleanFlow — Quality report: {name}</title>
<style>
 body{{font-family:-apple-system,'Segoe UI',Roboto,Arial,sans-serif;margin:0;background:#f5f7fb;color:#111827}}
 .wrap{{max-width:900px;margin:0 auto;padding:32px 20px}}
 h1{{font-size:22px;margin:0 0 4px}} h2{{font-size:16px;margin:28px 0 10px}}
 .sub{{color:#6b7280;font-size:13px}}
 .score{{display:flex;align-items:center;gap:16px;background:#fff;border:1px solid #e5e7eb;
        border-radius:12px;padding:18px;margin:18px 0}}
 .big{{font-size:40px;font-weight:800;color:{score_color}}}
 table{{border-collapse:collapse;width:100%;font-size:13px;background:#fff;
       border:1px solid #e5e7eb;border-radius:10px;overflow:hidden}}
 th,td{{padding:8px 12px;border-bottom:1px solid #f0f1f4;text-align:left;vertical-align:top}}
 th{{background:#f3f4f6;font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:#4b5563}}
 tr:last-child td{{border-bottom:none}}
 .muted{{color:#6b7280}} footer{{margin-top:28px;color:#9ca3af;font-size:11.5px}}
</style></head><body><div class="wrap">
<h1>Data Quality Report — {name}</h1>
<div class="sub">Generated by DataLab CleanFlow · {report['dataset'].get('updated_at') or ''}</div>

<div class="score">
 <div class="big">{ov_a['quality_score']}<span style="font-size:16px;color:#6b7280">/100</span></div>
 <div>
   <div><b>Grade: {_esc(ov_a['grade'])}</b></div>
   <div class="muted">Before cleaning: {ov_b['quality_score']}/100
     (change {dl['quality_score']:+d} points)</div>
 </div>
</div>

<h2>Before / after comparison</h2>
<table>
<tr><th>Metric</th><th>Before</th><th>After</th><th>Change</th></tr>
{metric_row("Quality score", ov_b['quality_score'], ov_a['quality_score'], dl['quality_score'])}
{metric_row("Rows", ov_b['rows'], ov_a['rows'], -(dl['rows_removed']))}
{metric_row("Columns", ov_b['cols'], ov_a['cols'], dl['columns_added'] - dl['columns_removed'])}
{metric_row("Missing cells", ov_b['missing_cells'], ov_a['missing_cells'], -dl['missing_handled'])}
{metric_row("Duplicate rows", ov_b['duplicate_rows'], ov_a['duplicate_rows'], -dl['duplicates_removed'])}
{metric_row("Memory (MB)", ov_b['memory_mb'], ov_a['memory_mb'])}
</table>

<h2>Cleaning summary</h2>
<table>
<tr><th colspan="2">Impact</th></tr>
<tr><td>Missing values removed or handled</td><td><b>{dl['missing_handled']}</b></td></tr>
<tr><td>Duplicate rows removed</td><td><b>{dl['duplicates_removed']}</b></td></tr>
<tr><td>Rows removed</td><td><b>{dl['rows_removed']}</b></td></tr>
<tr><td>Columns added / removed</td><td><b>+{dl['columns_added']} / -{dl['columns_removed']}</b></td></tr>
<tr><td>Outliers detected (before cleaning)</td><td><b>{dl['outliers_detected']}</b></td></tr>
</table>

<h2>Operation history</h2>
<table><tr><th>Time</th><th>Action</th><th>Summary</th><th>Score</th></tr>{ops_rows}</table>

<h2>Remaining issues</h2>
<table><tr><th>Severity</th><th>Issue</th><th>Detail</th></tr>{issues_rows}</table>

<h2>Column profile (after cleaning)</h2>
<table><tr><th>Column</th><th>Type</th><th>Missing</th><th>Unique</th><th>Outliers (IQR)</th></tr>
{cols_rows}</table>

<footer>Counts of removed rows use “before − after” differences; see the operation
history for the exact steps. Generated locally by DataLab — no data left this machine.</footer>
</div></body></html>"""
    return html.encode("utf-8")
