"""Core types for the signal layer."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SignalStatus(str, Enum):
    OK = "OK"
    NOT_AVAILABLE = "NotAvailable"
    ERROR = "Error"


@dataclass
class SignalResult:
    """Unified result from any signal provider."""
    signal_name: str
    status: SignalStatus
    items: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] | None = None
    error_msg: str = ""
    duration_ms: int = 0


@dataclass
class EvalScope:
    """Scope targeting for on-demand evaluation."""
    tenant_id: str | None = None
    management_group_id: str | None = None
    subscription_ids: list[str] = field(default_factory=list)
    resource_group: str | None = None


@dataclass
class ControlResult:
    """Deterministic result from a single control evaluator."""
    status: str  # Pass | Fail | Partial | Manual | Unknown | Error
    severity: str = "Medium"
    confidence: str = "High"
    reason: str = ""
    evidence: list[dict[str, Any]] = field(default_factory=list)
    signals_used: list[str] = field(default_factory=list)
    next_checks: list[dict[str, str]] = field(default_factory=list)


@dataclass
class EvalContext:
    """Runtime context passed into every evaluator."""
    scope: EvalScope
    run_id: str = ""
    options: dict[str, Any] = field(default_factory=dict)
