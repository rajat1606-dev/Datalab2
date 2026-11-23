"""Heuristic chart recommendations based on column roles.

Recommendations are ranked by simple rules (time columns -> line charts,
category + number -> bar charts, two numbers -> scatter, ...). Each
recommendation carries the full chart parameters so the UI can apply it with
one click.
"""
from typing import Dict, List

import pandas as pd

from services.dataframe import ROLE_CATEGORICAL, ROLE_DATETIME, ROLE_NUMERIC, ROLE_TEXT


def _usable_numeric(df: pd.DataFrame, col: str) -> bool:
    return pd.api.types.is_numeric_dtype(df[col]) and df[col].nunique(dropna=True) > 1


def _best_pair(corr: pd.DataFrame, nums: List[str]):
    best = (nums[0], nums[1] if len(nums) > 1 else nums[0])
    best_v = -1.0
    for i in range(len(nums)):
        for j in range(i + 1, len(nums)):
            v = corr.iloc[i, j]
            if pd.notna(v) and abs(v) > best_v:
                best_v = abs(v)
                best = (nums[i], nums[j])
    return best


def recommend_charts(df: pd.DataFrame, roles: Dict[str, str]) -> List[dict]:
    recs: List[dict] = []
    if df.empty:
        return recs

    nums = [c for c in df.columns if roles.get(c) == ROLE_NUMERIC and _usable_numeric(df, c)]
    cats = [c for c in df.columns
            if roles.get(c) == ROLE_CATEGORICAL and 1 < df[c].nunique(dropna=True) <= 40]
    dts = [c for c in df.columns if roles.get(c) == ROLE_DATETIME]
    texts = [c for c in df.columns
             if roles.get(c) == ROLE_TEXT and df[c].nunique(dropna=True) <= 20]

    def add(chart_type: str, score: int, title: str, reason: str, **params) -> None:
        recs.append({
            "chart_type": chart_type,
            "title": title,
            "reason": reason,
            "score": score,
            "params": {"chart_type": chart_type, "agg": "mean", "bins": 30,
                       "heatmap_mode": "correlation", **params},
        })

    if dts and nums:
        add("line", 96, f"Trend of {nums[0]} over {dts[0]}",
            f"'{dts[0]}' is a date column, so a line chart shows how '{nums[0]}' changes over time.",
            x=dts[0], y=nums[0])
    if cats and nums:
        add("bar", 93, f"{nums[0]} by {cats[0]}",
            f"Compare average '{nums[0]}' across the categories of '{cats[0]}'.",
            x=cats[0], y=nums[0])
    if nums:
        add("histogram", 88, f"Distribution of {nums[0]}",
            f"See how values of '{nums[0]}' are spread and where they concentrate.",
            x=nums[0])
    if len(nums) >= 2:
        corr = df[nums].corr(numeric_only=True)
        a, b = _best_pair(corr, nums)
        add("scatter", 85, f"{a} vs {b}",
            f"Explore the relationship between '{a}' and '{b}'.", x=a, y=b)
        add("heatmap", 80, "Correlation heatmap",
            f"Measure how strongly the {len(nums)} numeric columns relate to each other.")
    if cats and nums:
        add("box", 74, f"{nums[0]} spread by {cats[0]}",
            f"Compare the spread and outliers of '{nums[0]}' for each value of '{cats[0]}'.",
            x=cats[0], y=nums[0])
    if cats:
        add("pie", 70, f"Share of {cats[0]}",
            f"'{cats[0]}' has few distinct values — a pie chart shows their proportions.",
            x=cats[0])
    if len(cats) >= 2 and nums:
        add("heatmap", 62, f"{nums[0]} by {cats[0]} × {cats[1]}",
            "A pivot heatmap cross-tabulates two category columns against a value.",
            heatmap_mode="pivot", x=cats[0], y=cats[1], z=nums[0])
    if not nums and not cats and texts:
        add("bar", 60, f"Most common {texts[0]} values",
            f"Count the most frequent values of '{texts[0]}'.", x=texts[0])

    recs.sort(key=lambda r: -r["score"])
    return recs[:6]
