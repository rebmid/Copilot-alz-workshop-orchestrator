"""AI-layer domain types — architectural decision support contracts.

These TypedDicts define the shapes that flow between the reasoning engine,
MCP retriever, and prompt templates for the implementation-decision and
sequence-justification passes.

Follows the project convention (TypedDict, not Pydantic) so they compose
cleanly with the existing schemas/domain.py contracts.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


# ── ALZ Implementation Pattern ────────────────────────────────────
class ALZImplementationOption(TypedDict):
    """A single ALZ implementation pattern returned by MCP grounding."""
    pattern_name: str
    alz_module: str
    description: str
    prerequisites: List[str]
    learn_url: str


# ── Per-Initiative Implementation Decision ────────────────────────
class InitiativeImplementation(TypedDict):
    """Architectural decision record for one initiative.

    Populated by the Implementation Decision pass (Pass 3) where the LLM
    selects among ALZ implementation options grounded via MCP and justifies
    the choice against deterministic assessment evidence.
    """
    initiative_id: str
    initiative_title: str
    recommended_pattern: str
    alz_module: str
    why_this_pattern: str
    prerequisites_met: List[str]
    prerequisites_missing: List[str]
    sequence_justification: str
    operating_model_impact: str
    capability_unlocked: str
    next_engagement_alignment: str


# ── Sequence Justification (cross-initiative) ─────────────────────
class SequenceJustification(TypedDict):
    """Output of the Sequence Justification pass (Pass 4).

    Explains why initiatives are ordered the way they are in platform terms,
    not just dependency arrows.
    """
    sequence_rationale: str
    dependency_chain: List[Dict[str, Any]]
    parallel_opportunities: List[List[str]]
    platform_prerequisites: List[str]
    capability_unlock_order: List[str]
    risk_sequencing_notes: str


# ── Engagement Recommendation ─────────────────────────────────────
class EngagementRecommendation(TypedDict):
    """Maps assessment findings to CSA engagement motions."""
    engagement_type: str          # e.g. "CSA Workshop", "Architecture Review", "PoC"
    topic: str
    alz_design_area: str
    justification: str
    initiatives_addressed: List[str]
    priority: str                 # "High" | "Medium" | "Low"


# ── Enriched Payload Fields ──────────────────────────────────────
class DesignAreaMaturity(TypedDict):
    """Per-design-area maturity derived from section_scores."""
    design_area: str
    maturity_percent: float
    control_pass_rate: float
    top_gaps: List[str]


class PlatformScaleLimits(TypedDict):
    """Scale context derived from execution_context."""
    subscription_count: int
    management_group_depth: int
    identity_type: str
    rbac_highest_role: str
    multi_tenant: bool


class SignalConfidence(TypedDict):
    """Aggregated signal confidence for transparency."""
    total_signals_probed: int
    signals_available: int
    signals_unavailable: int
    availability_percent: float
    low_confidence_areas: List[str]
