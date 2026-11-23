"""Chart builders.

Each function validates the request against the dataset, computes the data
with pandas and returns a Plotly figure with the DataLab dark theme applied.
The frontend renders the figure JSON with plotly.js as-is.
"""
from typing import Dict, Optional

import pandas as pd
import plotly.express as px
from plotly.graph_objects import Figure

from services.dataframe import ROLE_CATEGORICAL, ROLE_DATETIME, ROLE_NUMERIC, DataError

CHART_TYPES = ("bar", "line", "pie", "histogram", "scatter", "box", "heatmap")
AGG_LABEL = {
    "mean": "Average",
    "sum": "Total",
    "count": "Count",
    "min": "Minimum",
    "max": "Maximum",
    "median": "Median",
}

# Shared dark theme (must match the CSS --chart-bg used by chart cards).
THEME = dict(
    paper_bgcolor="#0f172a",
    plot_bgcolor="#0f172a",
    font=dict(family="Inter, 'Segoe UI', system-ui, sans-serif", size=13, color="#9fb0c9"),
    colorway=["#3b82f6", "#22d3ee", "#a78bfa", "#34d399", "#fbbf24",
              "#fb7185", "#60a5fa", "#f472b6"],
    margin=dict(l=64, r=30, t=64, b=64),
    height=430,
    autosize=True,
    hoverlabel=dict(bgcolor="#1b2540", bordercolor="#33415e",
                    font=dict(color="#e7edf6", size=13)),
    legend=dict(bgcolor="rgba(0,0,0,0)", bordercolor="#33415e", borderwidth=1),
)
AXIS_STYLE = dict(
    gridcolor="#22304d",
    zerolinecolor="#33415e",
    linecolor="#33415e",
    tickfont=dict(color="#9fb0c9"),
    title_font=dict(color="#c6d2e4"),
)


def _theme(fig: Figure, title: str) -> None:
    fig.update_layout(**THEME)
    fig.update_layout(title=dict(text=title, font=dict(size=16, color="#e7edf6"),
                                 x=0.005, xanchor="left"))
    fig.update_xaxes(**AXIS_STYLE)
    fig.update_yaxes(**AXIS_STYLE)


def _agg_label(agg: str) -> str:
    return AGG_LABEL.get(agg, agg.title())


def _ensure_numeric(df: pd.DataFrame, roles: Dict[str, str], col: str, axis: str) -> None:
    if roles.get(col) != ROLE_NUMERIC or not pd.api.types.is_numeric_dtype(df[col]):
        raise DataError(f"{axis} column '{col}' must be numeric for this chart.")


def _grouped(df: pd.DataFrame, x: str, y: str, agg: str) -> pd.Series:
    d = df[[x, y]].dropna()
    g = d.groupby(x)[y]
    s = g.count() if agg == "count" else getattr(g, agg)()
    return s.sort_index() if pd.api.types.is_numeric_dtype(s.index) or \
        pd.api.types.is_datetime64_any_dtype(s.index) else s.sort_values(ascending=False)


# ---------------------------------------------------------------------------
# Individual chart builders
# ---------------------------------------------------------------------------

def _bar(df, roles, x, y, agg) -> Figure:
    if not x:
        raise DataError("Choose a column for the X axis.")
    if y:
        _ensure_numeric(df, roles, y, "Y")
        s = _grouped(df, x, y, agg)
        if s.empty:
            raise DataError("No data available after removing empty values.")
        s = s.head(400)
        title = f"{_agg_label(agg)} of {y} by {x}"
        fig = px.bar(x=s.index, y=s.values,
                     labels={"x": x, "y": f"{_agg_label(agg)} of {y}"})
    else:
        s = df[x].value_counts().sort_values(ascending=False).head(60)
        if s.empty:
            raise DataError("No data available in that column.")
        title = f"Count of records by {x}"
        fig = px.bar(x=s.index, y=s.values, labels={"x": x, "y": "Count"})
    _theme(fig, title)
    return fig


def _line(df, roles, x, y, agg) -> Figure:
    if not x or not y:
        raise DataError("Line charts need both an X column and a numeric Y column.")
    _ensure_numeric(df, roles, y, "Y")
    s = _grouped(df, x, y, agg)
    if s.empty:
        raise DataError("No data available after removing empty values.")
    s = s.head(2000)
    fig = px.line(x=s.index, y=s.values, markers=True,
                  labels={"x": x, "y": f"{_agg_label(agg)} of {y}"})
    _theme(fig, f"{_agg_label(agg)} of {y} across {x}")
    return fig


def _pie(df, roles, x, y, agg) -> Figure:
    if not x:
        raise DataError("Choose a column to slice the pie by.")
    if y:
        _ensure_numeric(df, roles, y, "Y")
        s = _grouped(df, x, y, agg)
        title = f"{_agg_label(agg)} of {y} by {x}"
    else:
        s = df[x].value_counts()
        title = f"Share of records by {x}"
    if s.empty:
        raise DataError("No data available in that column.")
    s = s.sort_values(ascending=False)
    if len(s) > 12:
        top = s.head(12)
        other = float(s.iloc[12:].sum())
        names = [str(i) for i in top.index] + ["Other"]
        vals = [float(v) for v in top.values] + [max(other, 0.0)]
    else:
        names = [str(i) for i in s.index]
        vals = [float(v) for v in s.values]
    fig = px.pie(names=names, values=vals, hole=0.45)
    _theme(fig, title)
    return fig


def _histogram(df, roles, x, bins) -> Figure:
    if not x:
        raise DataError("Choose a numeric column to plot the distribution of.")
    _ensure_numeric(df, roles, x, "X")
    d = df[[x]].dropna()
    if d.empty:
        raise DataError("That column has no numeric values to plot.")
    fig = px.histogram(d, x=x, nbins=bins, labels={"x": x, "y": "Count"})
    _theme(fig, f"Distribution of {x}")
    return fig


def _scatter(df, roles, x, y, group) -> Figure:
    if not x or not y:
        raise DataError("Scatter plots need both an X and a Y numeric column.")
    if x == y:
        raise DataError("X and Y must be different columns for a scatter plot.")
    _ensure_numeric(df, roles, x, "X")
    _ensure_numeric(df, roles, y, "Y")
    cols = [x, y] + ([group] if group else [])
    d = df[cols].dropna(subset=[x, y])
    if d.empty:
        raise DataError("No rows have values in both selected columns.")
    title = f"{x} vs {y}"
    if group:
        if roles.get(group) not in (ROLE_CATEGORICAL, ROLE_TEXT):
            raise DataError(f"Group by '{group}' should be a categorical column.")
        if d[group].nunique(dropna=True) > 25:
            raise DataError(f"'{group}' has too many unique values to group by (max 25).")
        title += f", by {group}"
    if len(d) > 5000:
        d = d.sample(5000, random_state=42)
        title += " (5,000 sampled points)"
    if group:
        fig = px.scatter(d, x=x, y=y, color=group)
    else:
        fig = px.scatter(d, x=x, y=y)
    fig.update_traces(marker=dict(size=7, opacity=0.75))
    _theme(fig, title)
    return fig


def _box(df, roles, x, y) -> Figure:
    if not y:
        raise DataError("Choose a numeric column for Y.")
    _ensure_numeric(df, roles, y, "Y")
    if x:
        d = df[[x, y]].dropna()
        if d.empty:
            raise DataError("No rows have values in both selected columns.")
        if d[x].nunique(dropna=True) > 40:
            raise DataError(f"'{x}' has too many unique values for a box plot (max 40).")
        fig = px.box(d, x=x, y=y)
        title = f"Distribution of {y} by {x}"
    else:
        d = df[[y]].dropna()
        if d.empty:
            raise DataError("That column has no values to plot.")
        fig = px.box(d, y=y)
        title = f"Distribution of {y}"
    _theme(fig, title)
    return fig


def _heatmap(df, roles, p: dict) -> Figure:
    x, y, z = p.get("x"), p.get("y"), p.get("z")
    agg = p.get("agg") or "mean"
    if p.get("heatmap_mode") == "pivot":
        if not (x and y and z):
            raise DataError("Pivot heatmap needs X, Y and a numeric Z (value) column.")
        _ensure_numeric(df, roles, z, "Z")
        d = df[[x, y, z]].dropna()
        if d.empty:
            raise DataError("No rows combine all three selected columns.")
        for axis_col in (x, y):
            n = int(d[axis_col].nunique())
            if n > 60:
                raise DataError(
                    f"'{axis_col}' has {n} unique values; pivot heatmaps support up to 60. "
                    "Pick a column with fewer categories."
                )
        pv = d.pivot_table(index=y, columns=x, values=z, aggfunc=agg)
        pv = pv.dropna(how="all").dropna(axis=1, how="all")
        if pv.empty:
            raise DataError("Not enough data to build the pivot table.")
        fig = px.imshow(pv.values, x=[str(c) for c in pv.columns],
                        y=[str(i) for i in pv.index], color_continuous_scale="Blues",
                        aspect="auto", text_auto=".2f", labels=dict(color=_agg_label(agg)))
        _theme(fig, f"{_agg_label(agg)} of {z} — {y} × {x}")
    else:
        nums = [c for c in df.columns
                if roles.get(c) == ROLE_NUMERIC and pd.api.types.is_numeric_dtype(df[c])]
        if len(nums) < 2:
            raise DataError("Correlation heatmap needs at least two numeric columns.")
        corr = df[nums].corr().round(3)
        fig = px.imshow(corr, text_auto=".2f", color_continuous_scale="RdBu_r",
                        zmin=-1, zmax=1, aspect="auto",
                        labels=dict(color="Correlation"))
        _theme(fig, "Correlation between numeric columns")
    return fig


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def build_figure(df: pd.DataFrame, roles: Dict[str, str], p: dict) -> Figure:
    """Validate chart parameters and build the figure."""
    if df.empty:
        raise DataError("This dataset has no rows to chart yet.")
    ctype = p.get("chart_type")
    x, y, z, group = p.get("x"), p.get("y"), p.get("z"), p.get("group")
    agg = p.get("agg") or "mean"
    for axis, col in (("X", x), ("Y", y), ("Z", z), ("Group", group)):
        if col and col not in df.columns:
            raise DataError(f"{axis} column '{col}' does not exist in this dataset.")

    if ctype == "bar":
        return _bar(df, roles, x, y, agg)
    if ctype == "line":
        return _line(df, roles, x, y, agg)
    if ctype == "pie":
        return _pie(df, roles, x, y, agg)
    if ctype == "histogram":
        return _histogram(df, roles, x, p.get("bins") or 30)
    if ctype == "scatter":
        return _scatter(df, roles, x, y, group)
    if ctype == "box":
        return _box(df, roles, x, y)
    if ctype == "heatmap":
        return _heatmap(df, roles, p)
    raise DataError(f"Unknown chart type '{ctype}'.")
