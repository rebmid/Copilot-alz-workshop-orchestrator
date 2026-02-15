"""Why-AI — turns a deterministic evidence payload into a causal narrative.

Separated from the deterministic reasoning layer so the --why pipeline
works identically with or without an AI provider.
"""
from __future__ import annotations

import json
from typing import Any


# ──────────────────────────────────────────────────────────────────
# Prompt template
# ──────────────────────────────────────────────────────────────────

_WHY_PROMPT = """\
You are a senior Azure Cloud Solution Architect performing a root-cause analysis.

The customer's Azure Landing Zone assessment identified **{domain}** as a top business risk.

## RISK
{risk_json}

## FAILING CONTROLS ({fail_count})
{controls_json}

## DEPENDENCY IMPACT
These failing controls block downstream controls:
{dependencies_json}

## ROADMAP ACTIONS THAT FIX THIS
{initiatives_json}

## INSTRUCTIONS
Produce a JSON object with these keys:
- "domain": the domain name
- "root_cause": A concise 2-3 sentence root-cause analysis explaining WHY this \
domain is the top risk. Do NOT use task-based language like "Enable X" or \
"Deploy Y". Describe the current state and its consequences.
- "business_impact": How this risk impacts the customer's business (security \
posture, compliance, operational reliability). Be specific to the evidence.
- "fix_sequence": An ordered array of objects, each with:
    - "step": integer (execution order)
    - "action": what to do (short imperative)
    - "why_this_order": why this step must come before the next
    - "initiative_id": the roadmap initiative ID (if applicable)
    - "learn_url": the Microsoft Learn URL for this step (from the grounding data)
- "cascade_effect": Describe which downstream controls will automatically \
improve once the root cause is fixed.

Return ONLY valid JSON. No markdown fences.
"""


def _build_prompt(payload: dict) -> str:
    """Build the full prompt from a deterministic payload."""
    return _WHY_PROMPT.format(
        domain=payload["domain"],
        risk_json=json.dumps(payload["risk"], indent=2),
        fail_count=len(payload["failing_controls"]),
        controls_json=json.dumps(payload["failing_controls"], indent=2),
        dependencies_json=json.dumps(payload["dependency_impact"], indent=2),
        initiatives_json=json.dumps(payload["roadmap_actions"], indent=2),
    )


# ──────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────

def generate_why_explanation(provider: Any, payload: dict, *, verbose: bool = True) -> dict:
    """Call the reasoning model and return the AI explanation dict.

    Parameters
    ----------
    provider : ReasoningProvider
        An object with a ``complete(prompt, context, max_tokens)`` method.
    payload : dict
        Output of ``build_why_payload()`` — must contain risk, failing_controls,
        dependency_impact, roadmap_actions.
    verbose : bool
        Print progress to stdout.

    Returns
    -------
    dict — the model's JSON response (root_cause, business_impact, fix_sequence,
    cascade_effect) or ``{"error": ...}`` on failure.
    """
    if verbose:
        print("  Sending evidence to reasoning model …")

    prompt = _build_prompt(payload)

    # Prepend system persona if available
    try:
        from ai.prompts import PromptPack
        system = PromptPack().system
        prompt = f"{system}\n---SYSTEM---\n{prompt}"
    except Exception:
        pass  # works fine without the system preamble

    try:
        explanation = provider.complete(prompt, payload, max_tokens=4000)
        if verbose:
            print("  ✓ AI explanation generated")
        return explanation
    except Exception as e:
        if verbose:
            print(f"  ⚠ AI explanation failed: {e}")
        return {"error": str(e)}
