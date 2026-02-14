"""Core domain types — shared contracts used across the entire assessment system.

These are the canonical shapes that cross layer boundaries.
Internal layers (evaluators, signals) may use richer dataclasses,
but everything that leaves a layer must conform to these contracts.
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, TypedDict


# ── Status literals ───────────────────────────────────────────────
ControlStatus = Literal["Pass", "Fail", "Partial", "Manual", "Unknown", "Deferred", "Error"]
Confidence = Literal["Low", "Medium", "High"]


# ── Control result — deterministic engine output ──────────────────
class ControlResult(TypedDict):
    """Result from evaluating a single control.  No AI involved."""
    control_id: str
    status: ControlStatus
    severity: str
    reason: str
    evidence: List[dict]
    confidence: Confidence
    signals_used: List[str]


# ── Intent result — aggregated outcome for a workshop intent ──────
class IntentResult(TypedDict):
    """Aggregated result for an intent bundle (e.g. enterprise_scale_readiness)."""
    intent: str
    status: Literal["Ready", "NotReady", "Partial"]
    summary: str
    controls_evaluated: int
    passed_controls: List[str]
    failed_controls: List[str]
    deferred_controls: List[str]
    data_confidence: Confidence
    discipline_scores: Dict[str, Any]


# ── Scoring-compatible flat result (consumed by engine/scoring.py) ─
class ScoringResult(TypedDict):
    """Shape expected by compute_scoring(), rollup_by_section(), and reports."""
    control_id: str
    section: str
    category: str
    text: str
    question: str
    severity: str
    status: str
    evidence_count: int
    evidence: List[dict]
    signal_used: Optional[str]
    confidence: str
    notes: str
