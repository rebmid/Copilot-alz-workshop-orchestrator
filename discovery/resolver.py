"""Discovery resolver — interactive workshop engine.

Walks the user through relevant decision-tree questions in the terminal,
collects answers, resolves Manual controls to Pass/Partial/Fail, and
returns an updated results list + workshop metadata.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from discovery.loader import DecisionTree, TreeQuestion, load_relevant_trees
from engine.scoring import compute_scoring


# ── Answer → status mapping ───────────────────────────────────────

_YES_NO_MAP = {
    "yes": "Pass",
    "y":   "Pass",
    "partial": "Partial",
    "p":   "Partial",
    "no":  "Fail",
    "n":   "Fail",
}

_MATURITY_STATUS = {
    "1": "Fail",
    "2": "Partial",
    "3": "Pass",
}


# ── Terminal prompting helpers ────────────────────────────────────

def _prompt_yes_no(question: TreeQuestion) -> tuple[str, str]:
    """Prompt for yes/no/partial.  Returns (answer_key, status)."""
    while True:
        ans = input("  → [Y]es / [P]artial / [N]o: ").strip().lower()
        status = _YES_NO_MAP.get(ans)
        if status:
            key = {"y": "yes", "p": "partial", "n": "no"}.get(ans, ans)
            return key, status
        print("    Please enter Y, P, or N.")


def _prompt_maturity(question: TreeQuestion) -> tuple[str, str]:
    """Prompt for 1/2/3 maturity scale.  Returns (answer_key, status)."""
    while True:
        ans = input("  → Enter 1, 2, or 3: ").strip()
        status = _MATURITY_STATUS.get(ans)
        if status:
            return ans, status
        print("    Please enter 1, 2, or 3.")


def _prompt_question(question: TreeQuestion) -> tuple[str, str]:
    """Dispatch to the right prompter based on question type."""
    if question.qtype == "maturity_scale":
        return _prompt_maturity(question)
    return _prompt_yes_no(question)


# ── Workshop session ──────────────────────────────────────────────

class WorkshopAnswer:
    """Captures one answered question."""
    __slots__ = ("question_id", "tree_id", "answer_key", "status",
                 "resolved_control_ids", "weight", "timestamp")

    def __init__(self, question_id: str, tree_id: str, answer_key: str,
                 status: str, resolved_control_ids: list[str], weight: float):
        self.question_id = question_id
        self.tree_id = tree_id
        self.answer_key = answer_key
        self.status = status
        self.resolved_control_ids = resolved_control_ids
        self.weight = weight
        self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "question_id": self.question_id,
            "tree_id": self.tree_id,
            "answer_key": self.answer_key,
            "status": self.status,
            "resolved_control_ids": self.resolved_control_ids,
            "weight": self.weight,
            "timestamp": self.timestamp,
        }


class WorkshopSession:
    """Interactive workshop that walks through decision trees."""

    def __init__(self, results: list[dict], *, verbose: bool = True):
        self.results = results
        self.verbose = verbose
        self._results_by_id: dict[str, dict] = {
            r["control_id"]: r for r in results if "control_id" in r
        }
        self._manual_ids: set[str] = {
            cid for cid, r in self._results_by_id.items()
            if r.get("status") == "Manual"
        }
        self.answers: list[WorkshopAnswer] = []
        self._resolved_ids: set[str] = set()

    @property
    def manual_before(self) -> int:
        return len(self._manual_ids)

    @property
    def resolved_count(self) -> int:
        return len(self._resolved_ids)

    @property
    def manual_remaining(self) -> int:
        return len(self._manual_ids - self._resolved_ids)

    def run(self) -> list[dict]:
        """Drive the workshop interactively.  Returns updated results list."""
        if not self._manual_ids:
            print("\n  No Manual controls to resolve — workshop complete.")
            return self.results

        trees = load_relevant_trees(self._manual_ids)
        if not trees:
            print("\n  No decision trees match the outstanding Manual controls.")
            return self.results

        total_questions = sum(
            len(t.relevant_questions(self._manual_ids)) for t in trees
        )

        print(f"\n╔══════════════════════════════════════╗")
        print(f"║   Discovery Workshop                 ║")
        print(f"╚══════════════════════════════════════╝")
        print(f"  Manual controls to resolve: {self.manual_before}")
        print(f"  Decision trees loaded:      {len(trees)}")
        print(f"  Questions to ask:           {total_questions}")
        print(f"  (Press Ctrl+C at any time to save partial progress)\n")

        try:
            for tree in trees:
                self._run_tree(tree)
        except KeyboardInterrupt:
            print("\n\n  ⚠ Workshop interrupted — saving partial answers.")

        # Apply answers to results
        self._apply_answers()

        # Summary
        print(f"\n  ─── Workshop Summary ─────────────────")
        print(f"  Questions answered:    {len(self.answers)}")
        print(f"  Controls resolved:     {self.resolved_count}")
        print(f"  Manual remaining:      {self.manual_remaining}")
        completion = round(
            self.resolved_count / self.manual_before * 100, 1
        ) if self.manual_before else 100.0
        print(f"  Workshop completion:   {completion}%")

        return self.results

    def _run_tree(self, tree: DecisionTree):
        """Walk one decision tree's questions."""
        questions = tree.relevant_questions(self._manual_ids - self._resolved_ids)
        if not questions:
            return

        print(f"  ── {tree.domain} ({len(questions)} questions) ──\n")

        for i, q in enumerate(questions, 1):
            # Skip if all controls already resolved by earlier answers
            remaining = q.all_control_ids & (self._manual_ids - self._resolved_ids)
            if not remaining:
                continue

            print(f"  [{i}/{len(questions)}] {q.text}")
            answer_key, status = _prompt_question(q)

            # Determine which control IDs this answer resolves
            resolved_ids = q.resolves.get(answer_key, [])
            # For maturity scale, answer_key is "1"/"2"/"3"
            if not resolved_ids:
                resolved_ids = list(remaining)

            # Only count controls that are actually still Manual
            effective_ids = [cid for cid in resolved_ids if cid in self._manual_ids]

            answer = WorkshopAnswer(
                question_id=q.id,
                tree_id=tree.id,
                answer_key=answer_key,
                status=status,
                resolved_control_ids=effective_ids,
                weight=q.weight,
            )
            self.answers.append(answer)
            self._resolved_ids.update(effective_ids)

            if self.verbose:
                print(f"    → {status} ({len(effective_ids)} control(s) resolved)\n")

    def _apply_answers(self):
        """Overwrite Manual results with workshop-determined statuses."""
        # Build control_id → best status map (last answer wins, but
        # higher-weight answers take precedence)
        overrides: dict[str, tuple[str, float, str]] = {}  # cid → (status, weight, q_id)
        for a in self.answers:
            for cid in a.resolved_control_ids:
                existing = overrides.get(cid)
                if existing is None or a.weight >= existing[1]:
                    overrides[cid] = (a.status, a.weight, a.question_id)

        # Apply
        for cid, (status, weight, q_id) in overrides.items():
            if cid in self._results_by_id:
                r = self._results_by_id[cid]
                r["status"] = status
                r["source"] = "workshop"
                r["workshop_question_id"] = q_id
                r["confidence"] = "High" if status in ("Pass", "Fail") else "Medium"
                r["confidence_score"] = 0.95 if status in ("Pass", "Fail") else 0.7
                r["notes"] = (r.get("notes") or "") + f" [Workshop: {status} via {q_id}]"

    def build_metadata(self) -> dict:
        """Return workshop session metadata for the run JSON."""
        completion = round(
            self.resolved_count / self.manual_before * 100, 1
        ) if self.manual_before else 100.0

        return {
            "workshop_completed": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "manual_before": self.manual_before,
            "controls_resolved": self.resolved_count,
            "manual_remaining": self.manual_remaining,
            "completion_percent": completion,
            "questions_answered": len(self.answers),
            "answers": [a.to_dict() for a in self.answers],
            "trees_used": list({a.tree_id for a in self.answers}),
            "confidence_level": (
                "High" if completion >= 80
                else "Medium" if completion >= 40
                else "Low"
            ),
        }


# ── Public entry point ────────────────────────────────────────────

def run_workshop(run_data: dict, *, verbose: bool = True) -> dict:
    """
    Run the interactive discovery workshop on an existing assessment.

    1. Loads the results from *run_data*
    2. Shows only trees/questions relevant to Manual controls
    3. Prompts the user for answers
    4. Updates control results (source="workshop")
    5. Re-runs the scoring engine
    6. Returns the updated run dict (ready to persist)
    """
    results = run_data.get("results", [])
    session = WorkshopSession(results, verbose=verbose)
    updated_results = session.run()

    # Overwrite results in-place
    run_data["results"] = updated_results

    # Re-run scoring
    scoring = compute_scoring(updated_results)
    run_data["scoring"] = scoring

    # Attach workshop metadata
    workshop_meta = session.build_metadata()
    run_data["workshop"] = workshop_meta

    # Update meta
    meta = run_data.setdefault("meta", {})
    meta["workshop_applied"] = True
    meta["workshop_timestamp"] = workshop_meta["timestamp"]

    return run_data
