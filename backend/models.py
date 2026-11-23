"""Pydantic request models (input validation for the API)."""
from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field

Cell = Optional[Union[str, float, int]]


class ColumnIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    type: Literal["text", "number", "date", "categorical"] = "text"


class ManualDataIn(BaseModel):
    columns: List[ColumnIn] = Field(min_length=1, max_length=60)
    rows: List[List[Cell]] = Field(default_factory=list)


class ManualDatasetIn(ManualDataIn):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=300)


class DatasetMetaIn(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    description: Optional[str] = Field(default=None, max_length=300)


class CleanOp(BaseModel):
    type: Literal["fill_missing", "drop_missing", "drop_duplicates", "convert_type"]
    columns: List[str] = Field(default_factory=list)
    strategy: Optional[Literal["mean", "median", "mode", "ffill", "bfill", "constant"]] = None
    value: Optional[Cell] = None
    how: Optional[Literal["any", "all"]] = "any"
    keep: Optional[Literal["first", "last"]] = "first"
    target: Optional[Literal["number", "date", "text", "categorical"]] = None


class CleanIn(BaseModel):
    operations: List[CleanOp] = Field(min_length=1, max_length=50)


class ChartIn(BaseModel):
    chart_type: Literal["bar", "line", "pie", "histogram", "scatter", "box", "heatmap"]
    x: Optional[str] = None
    y: Optional[str] = None
    z: Optional[str] = None
    group: Optional[str] = None
    agg: Literal["mean", "sum", "count", "min", "max", "median"] = "mean"
    bins: int = Field(default=30, ge=2, le=200)
    heatmap_mode: Literal["correlation", "pivot"] = "correlation"
