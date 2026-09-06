"""Pydantic v2 schemas for Nightly Synthesis & Graph Dream Cycle.

Enforces strict immutability, zero-crash deserialization, and forbidden extra fields.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict


class ConsolidationStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    DRY_RUN = "dry_run"


class ConsolidationMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    total_nodes_scanned: int = Field(ge=0)
    total_edges_scanned: int = Field(ge=0)
    communities_detected: int = Field(ge=0)
    themes_generated: int = Field(ge=0)
    themes_preserved: int = Field(ge=0)
    edges_decayed: int = Field(ge=0)
    edges_pruned: int = Field(ge=0)
    triangular_tensions_found: int = Field(ge=0)
    inquiries_generated: int = Field(ge=0)
    inquiries_active: int = Field(ge=0, le=3)  # Strictly bounded to <= 3 active inquiries


class ConsolidationReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    status: ConsolidationStatus
    started_at: datetime
    completed_at: datetime
    duration_ms: int = Field(ge=0)
    dry_run: bool = False
    metrics: ConsolidationMetrics
    errors: list[str] = Field(default_factory=list)


class ThemeSynthesisResult(BaseModel):
    """Structured output from Gemini Flash Fallback Ladder."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str = Field(min_length=5, max_length=120)
    summary: str = Field(min_length=20, max_length=300)
    body_markdown: str = Field(min_length=100)
    suggested_slug: str


class TriangularTensionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    triad_id: str
    node_a: str
    node_b: str
    node_c: str
    edge_ab_type: str
    edge_bc_type: str
    edge_ca_type: str
    contradiction_summary: str
    confidence: float = Field(ge=0.0, le=1.0)
    detected_at: datetime


class SocraticInquiryRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    target_concept: str
    question: str
    rationale: str
    status: str = Field(pattern="^(active|resolved|archived)$")
    created_at: datetime
    resolved_at: datetime | None = None
