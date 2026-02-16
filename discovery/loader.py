"""Discovery tree loader — finds and loads decision tree JSON files.

Each tree file lives in discovery/trees/ and maps workshop questions
to the Manual controls they can resolve.  The loader only returns trees
whose ``resolves`` control-ID sets intersect with the supplied set of
manual control IDs, so the workshop only shows relevant questions.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Set

_TREE_DIR = Path(__file__).resolve().parent / "trees"


# ── Data shapes ───────────────────────────────────────────────────

class TreeQuestion:
    """One question node inside a decision tree."""

    __slots__ = ("id", "text", "qtype", "resolves", "weight")

    def __init__(self, raw: dict):
        self.id: str = raw["id"]
        self.text: str = raw["text"]
        self.qtype: str = raw.get("type", "yes_no")
        self.resolves: dict[str, list[str]] = raw.get("resolves", {})
        self.weight: float = raw.get("weight", 1.0)

    @property
    def all_control_ids(self) -> set[str]:
        """Union of every control ID referenced by any answer branch."""
        ids: set[str] = set()
        for branch_ids in self.resolves.values():
            ids.update(branch_ids)
        return ids


class DecisionTree:
    """A single decision tree (one domain / JSON file)."""

    __slots__ = ("id", "domain", "description", "questions")

    def __init__(self, raw: dict):
        self.id: str = raw["id"]
        self.domain: str = raw["domain"]
        self.description: str = raw.get("description", "")
        self.questions: list[TreeQuestion] = [
            TreeQuestion(q) for q in raw.get("questions", [])
        ]

    @property
    def all_control_ids(self) -> set[str]:
        ids: set[str] = set()
        for q in self.questions:
            ids.update(q.all_control_ids)
        return ids

    def relevant_questions(self, manual_ids: set[str]) -> list[TreeQuestion]:
        """Return only questions whose resolved controls overlap *manual_ids*."""
        return [q for q in self.questions if q.all_control_ids & manual_ids]


# ── Public API ────────────────────────────────────────────────────

def load_all_trees() -> list[DecisionTree]:
    """Load every ``*.json`` in the trees/ directory."""
    trees: list[DecisionTree] = []
    if not _TREE_DIR.is_dir():
        return trees
    for fp in sorted(_TREE_DIR.glob("*.json")):
        raw = json.loads(fp.read_text(encoding="utf-8"))
        trees.append(DecisionTree(raw))
    return trees


def load_relevant_trees(manual_control_ids: set[str]) -> list[DecisionTree]:
    """Return only trees that resolve at least one of *manual_control_ids*."""
    return [
        t for t in load_all_trees()
        if t.all_control_ids & manual_control_ids
    ]
