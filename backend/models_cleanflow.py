"""Pydantic request models for the CleanFlow API (DataLab 2.0).

Deliberately tolerant: operations carry a bag of optional parameters because a
single generic model is validated against the operation registry at runtime
(unknown fields are ignored, wrong values raise clean 400 errors).
"""
from typing import List, Optional, Union

from pydantic import BaseModel, Field

Cell = Optional[Union[str, float, int]]


class CFOp(BaseModel):
    """One cleaning/transformation step (same shape as the registry)."""
    type: str = Field(min_length=1, max_length=60)
    columns: List[str] = Field(default_factory=list, max_length=200)
    column: Optional[str] = Field(default=None, max_length=200)
    new_name: Optional[str] = Field(default=None, max_length=120)
    strategy: Optional[str] = None
    value: Optional[Cell] = None
    how: Optional[str] = None
    keep: Optional[str] = None
    target: Optional[str] = None
    date_format: Optional[str] = Field(default=None, max_length=60)
    unified_format: Optional[str] = Field(default=None, max_length=60)
    trim: Optional[bool] = None
    collapse: Optional[bool] = None
    case: Optional[str] = None
    method: Optional[str] = None
    threshold: Optional[float] = Field(default=None, gt=0, le=1000)
    similarity: Optional[float] = Field(default=None, ge=0.5, le=1.0)
    action: Optional[str] = None
    on_error: Optional[str] = None
    dayfirst: Optional[bool] = None
    values: List[Cell] = Field(default_factory=list, max_length=100)
    fill_value: Optional[Cell] = None
    remove_rows: Optional[bool] = None
    drop_first: Optional[bool] = None
    title: Optional[str] = Field(default=None, max_length=120)
    approved: bool = False


class CFApplyIn(BaseModel):
    operations: List[CFOp] = Field(min_length=1, max_length=40)


class CFPipelineStepIn(CFOp):
    pass


class CFPipelinePreviewIn(BaseModel):
    steps: List[CFPipelineStepIn] = Field(min_length=1, max_length=40)


class CFPipelineRunIn(BaseModel):
    steps: List[CFPipelineStepIn] = Field(min_length=1, max_length=40)
    result_name: Optional[str] = Field(default=None, max_length=80)


class CFPipelineSaveIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=300)
    steps: List[CFPipelineStepIn] = Field(min_length=1, max_length=40)
