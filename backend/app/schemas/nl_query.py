"""
Schemas for the natural-language query endpoint.

POST /query
  Accept a plain-English question about traffic/vehicle data.
  Return structured results plus a plain-English summary.
"""

from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class NLQueryRequest(BaseModel):
    question: str = Field(
        ...,
        min_length=3,
        max_length=500,
        example="Which vehicles were spotted at Ameerpet Junction in the last 2 hours?",
    )


class NLQueryResultRow(BaseModel):
    """One row of tabular query results — column names vary by intent."""
    data: Dict[str, Any]


class NLQueryResponse(BaseModel):
    """
    Response for POST /query

    Fields
    ------
    question        : echoed back for display
    interpreted_as  : human-readable description of how the query was parsed
    intent          : machine tag (vehicles_at_location | time_range | plate_lookup |
                      count_at_location | suspicious | multi_camera | recent | help)
    answer_text     : one-sentence plain-English answer (show this prominently in the UI)
    columns         : ordered column names for table rendering
    rows            : result rows (empty list when count/summary answer is complete in answer_text)
    total_results   : total matching rows (may exceed len(rows) if capped)
    parameters      : parsed parameters so the UI can show "Searched: camera=CAM_001, after=..."
    confidence      : HIGH | MEDIUM | LOW — how sure the parser is about the intent
    suggestions     : alternative phrasings or follow-up questions to show in the UI
    generated_at    : server timestamp
    """
    question        : str                   = Field(..., example="vehicles at Ameerpet last hour")
    interpreted_as  : str                   = Field(..., example="Vehicles detected at Ameerpet Junction (CAM_001) in the last 1 hour")
    intent          : str                   = Field(..., example="vehicles_at_location")
    answer_text     : str                   = Field(..., example="Found 12 vehicles at Ameerpet Junction in the last 1 hour.")
    columns         : List[str]             = Field(default_factory=list)
    rows            : List[Dict[str, Any]]  = Field(default_factory=list)
    total_results   : int                   = Field(default=0)
    parameters      : Dict[str, Any]        = Field(default_factory=dict)
    confidence      : str                   = Field(default="HIGH", description="HIGH | MEDIUM | LOW")
    suggestions     : List[str]             = Field(default_factory=list)
    generated_at    : datetime              = Field(default_factory=datetime.utcnow)
