"""Control Knowledge Graph — dependency-aware planning for control evaluation.

Usage:
    from graph.knowledge_graph import ControlKnowledgeGraph
    kg = ControlKnowledgeGraph()
    plan = kg.plan_evaluation("enterprise_readiness")
    # plan.ordered_controls  -> topologically sorted control short IDs
    # plan.required_signals  -> deduplicated signal list
    # plan.deferred          -> controls that are deferred because a parent failed
"""
from __future__ import annotations

import json
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ── Data classes ──────────────────────────────────────────────────

@dataclass
class ControlNode:
    """Single node in the knowledge graph."""
    short_id: str
    full_id: str
    name: str
    evaluator_module: str
    requires_signals: list[str]
    depends_on: list[str]         # short IDs of parent controls
    defer_if_parent_fails: bool
    affects: list[dict[str, Any]]  # [{discipline, weight}]
    caf_reference: str | None
    question_resolvers: list[str]


@dataclass
class EvalPlan:
    """Output of the planning algorithm."""
    intent: str
    ordered_controls: list[str]     # topologically sorted short IDs
    required_signals: list[str]     # deduplicated, fetch-order
    deferred: list[str]             # controls deferred due to parent failures
    discipline_weights: dict[str, float]  # aggregated discipline → weight
    question_resolvers: list[str]   # unique question IDs relevant to this plan


@dataclass
class DeferredControl:
    """A control that was skipped because a parent failed/errored."""
    control_id: str
    reason: str
    failed_parent: str


# ── Knowledge Graph ──────────────────────────────────────────────

class ControlKnowledgeGraph:
    """
    Loads the control dependency graph from controls.json and provides:
    - plan_evaluation(intent) → topologically sorted EvalPlan
    - plan_from_ids(control_ids) → EvalPlan for arbitrary control set
    - get_dependents(control_id) → downstream controls
    - get_questions_for(control_ids) → question resolvers
    - discipline_score(results) → per-discipline weighted scores
    """

    def __init__(self, graph_path: str | Path | None = None):
        if graph_path is None:
            graph_path = Path(__file__).parent / "controls.json"
        self._path = Path(graph_path)
        self._raw: dict[str, Any] = {}
        self._nodes: dict[str, ControlNode] = {}
        self._bundles: dict[str, list[str]] = {}
        self._questions: dict[str, dict[str, Any]] = {}
        self._caf: dict[str, str] = {}
        self._load()

    # ── Loading ───────────────────────────────────────────────────

    def _load(self) -> None:
        with open(self._path, encoding="utf-8") as f:
            self._raw = json.load(f)

        self._caf = self._raw.get("caf_disciplines", {})
        self._questions = self._raw.get("question_resolvers", {})

        for sid, cdata in self._raw.get("controls", {}).items():
            self._nodes[sid] = ControlNode(
                short_id=sid,
                full_id=cdata["full_id"],
                name=cdata["name"],
                evaluator_module=cdata["evaluator_module"],
                requires_signals=cdata["requires_signals"],
                depends_on=cdata.get("depends_on", []),
                defer_if_parent_fails=cdata.get("defer_if_parent_fails", False),
                affects=cdata.get("affects", []),
                caf_reference=cdata.get("caf_reference"),
                question_resolvers=cdata.get("question_resolvers", []),
            )

        for bundle_id, bdata in self._raw.get("intent_bundles", {}).items():
            self._bundles[bundle_id] = bdata["controls"]

    # ── Public API ────────────────────────────────────────────────

    @property
    def controls(self) -> dict[str, ControlNode]:
        return dict(self._nodes)

    @property
    def bundle_names(self) -> list[str]:
        return list(self._bundles.keys())

    def get_bundle(self, intent: str) -> dict[str, Any] | None:
        bdata = self._raw.get("intent_bundles", {}).get(intent)
        return bdata

    def resolve_full_id(self, short_id: str) -> str | None:
        """Map 8-char short ID to full GUID."""
        node = self._nodes.get(short_id)
        return node.full_id if node else None

    def get_node(self, short_id: str) -> ControlNode | None:
        return self._nodes.get(short_id)

    def get_dependents(self, short_id: str) -> list[str]:
        """Return controls that depend on the given control."""
        return [
            n.short_id for n in self._nodes.values()
            if short_id in n.depends_on
        ]

    def get_ancestors(self, short_id: str) -> list[str]:
        """Return all transitive ancestors (dependencies) of a control."""
        visited: set[str] = set()
        queue = deque(self._nodes.get(short_id, ControlNode(
            short_id="", full_id="", name="", evaluator_module="",
            requires_signals=[], depends_on=[], defer_if_parent_fails=False,
            affects=[], caf_reference=None, question_resolvers=[],
        )).depends_on)
        while queue:
            parent = queue.popleft()
            if parent in visited:
                continue
            visited.add(parent)
            pnode = self._nodes.get(parent)
            if pnode:
                queue.extend(pnode.depends_on)
        return list(visited)

    # ── Planning ──────────────────────────────────────────────────

    def plan_evaluation(self, intent: str) -> EvalPlan:
        """
        Create an evaluation plan from a named intent bundle.
        Returns topologically sorted controls with dependency resolution.
        """
        control_ids = self._bundles.get(intent)
        if control_ids is None:
            raise ValueError(
                f"Unknown intent: {intent!r}. "
                f"Available: {', '.join(self._bundles.keys())}"
            )
        return self.plan_from_ids(control_ids, intent=intent)

    def plan_from_ids(
        self,
        control_ids: list[str],
        *,
        intent: str = "custom",
    ) -> EvalPlan:
        """
        Build an evaluation plan for an arbitrary set of controls.
        Automatically includes transitive dependencies.
        """
        # Expand to include all transitive dependencies
        expanded = set(control_ids)
        for cid in list(expanded):
            expanded.update(self.get_ancestors(cid))

        # Keep only controls that actually exist in the graph
        valid = [cid for cid in expanded if cid in self._nodes]

        # Topological sort (Kahn's algorithm)
        ordered = self._topo_sort(valid)

        # Collect required signals (deduped, preserving first-seen order)
        seen_signals: set[str] = set()
        signal_order: list[str] = []
        for cid in ordered:
            node = self._nodes[cid]
            for sig in node.requires_signals:
                if sig not in seen_signals:
                    seen_signals.add(sig)
                    signal_order.append(sig)

        # Collect discipline weights
        disc_weights: dict[str, float] = defaultdict(float)
        for cid in ordered:
            node = self._nodes[cid]
            for aff in node.affects:
                disc_weights[aff["discipline"]] += aff["weight"]

        # Collect question resolvers
        qr_set: set[str] = set()
        for cid in ordered:
            node = self._nodes[cid]
            qr_set.update(node.question_resolvers)

        return EvalPlan(
            intent=intent,
            ordered_controls=ordered,
            required_signals=signal_order,
            deferred=[],  # filled at runtime by execute_plan()
            discipline_weights=dict(disc_weights),
            question_resolvers=sorted(qr_set),
        )

    def apply_deferrals(
        self,
        plan: EvalPlan,
        results: dict[str, dict[str, Any]],
    ) -> list[DeferredControl]:
        """
        Given evaluation results so far, determine which remaining controls
        should be deferred because a parent failed or errored.

        Returns list of DeferredControl. Also updates plan.deferred.
        """
        deferred: list[DeferredControl] = []
        failed = {
            cid for cid, res in results.items()
            if res.get("status") in ("Fail", "Error")
        }

        for cid in plan.ordered_controls:
            if cid in results:
                continue  # already evaluated
            node = self._nodes.get(cid)
            if node and node.defer_if_parent_fails:
                failed_parents = [p for p in node.depends_on if p in failed]
                if failed_parents:
                    deferred.append(DeferredControl(
                        control_id=cid,
                        reason=f"Deferred: parent {failed_parents[0]} failed",
                        failed_parent=failed_parents[0],
                    ))

        plan.deferred = [d.control_id for d in deferred]
        return deferred

    # ── Question Resolvers ────────────────────────────────────────

    def get_questions_for(
        self,
        control_ids: list[str],
        *,
        only_failed: dict[str, dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Return question resolver records relevant to the given controls.

        If only_failed is provided, only return questions that resolve
        controls in the failed set (to avoid asking unnecessary questions).
        """
        qr_ids: set[str] = set()
        for cid in control_ids:
            node = self._nodes.get(cid)
            if node:
                qr_ids.update(node.question_resolvers)

        questions = []
        for qr_id in sorted(qr_ids):
            qr = self._questions.get(qr_id)
            if qr is None:
                continue

            # If filtering to failed controls, skip irrelevant questions
            if only_failed is not None:
                resolves = qr.get("resolves_controls", [])
                has_failed = any(c in only_failed for c in resolves)
                if not has_failed:
                    continue

            questions.append({
                "id": qr_id,
                "question": qr["question"],
                "resolves_controls": qr.get("resolves_controls", []),
                "resolution_effect": qr.get("resolution_effect", ""),
            })

        return questions

    # ── Discipline Scoring ────────────────────────────────────────

    def discipline_score(
        self,
        results: dict[str, dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        """
        Compute per-discipline weighted scores from evaluation results.

        Returns:
            {discipline: {score: 0-100, weight_total, pass_weight, controls_counted}}
        """
        disc: dict[str, dict[str, float]] = defaultdict(
            lambda: {"weight_total": 0.0, "pass_weight": 0.0, "counted": 0}
        )

        for cid, res in results.items():
            node = self._nodes.get(cid)
            if node is None:
                continue
            status = res.get("status", "Unknown")
            is_pass = status == "Pass"
            is_partial = status == "Partial"

            for aff in node.affects:
                d = aff["discipline"]
                w = aff["weight"]
                disc[d]["weight_total"] += w
                disc[d]["counted"] += 1
                if is_pass:
                    disc[d]["pass_weight"] += w
                elif is_partial:
                    disc[d]["pass_weight"] += w * 0.5

        out = {}
        for d, data in disc.items():
            total = data["weight_total"]
            score = round((data["pass_weight"] / total) * 100) if total > 0 else 0
            out[d] = {
                "discipline": d,
                "discipline_label": self._caf.get(d, d),
                "score": score,
                "weight_total": round(total, 3),
                "pass_weight": round(data["pass_weight"], 3),
                "controls_counted": int(data["counted"]),
            }
        return out

    # ── Signal Dependency Analysis ────────────────────────────────

    def signal_sharing_analysis(self, control_ids: list[str]) -> dict[str, list[str]]:
        """
        For a set of controls, show which signals are shared across controls.
        Useful for demonstrating cache efficiency.
        """
        signal_to_controls: dict[str, list[str]] = defaultdict(list)
        for cid in control_ids:
            node = self._nodes.get(cid)
            if node:
                for sig in node.requires_signals:
                    signal_to_controls[sig].append(cid)
        return dict(signal_to_controls)

    # ── Internal ──────────────────────────────────────────────────

    def _topo_sort(self, control_ids: list[str]) -> list[str]:
        """
        Kahn's algorithm for topological sort.
        Respects depends_on within the given control set.
        """
        id_set = set(control_ids)

        # Build adjacency within the set
        in_degree: dict[str, int] = {cid: 0 for cid in id_set}
        adj: dict[str, list[str]] = {cid: [] for cid in id_set}

        for cid in id_set:
            node = self._nodes[cid]
            for parent in node.depends_on:
                if parent in id_set:
                    adj[parent].append(cid)
                    in_degree[cid] += 1

        # Start with zero in-degree nodes
        queue = deque(sorted(cid for cid, d in in_degree.items() if d == 0))
        result: list[str] = []

        while queue:
            current = queue.popleft()
            result.append(current)
            for child in sorted(adj.get(current, [])):
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    queue.append(child)

        # If there are remaining nodes, there's a cycle — just append them
        remaining = [cid for cid in id_set if cid not in set(result)]
        result.extend(sorted(remaining))

        return result

    # ── Serialization ─────────────────────────────────────────────

    def to_summary(self) -> dict[str, Any]:
        """Return a summary of the graph for diagnostics / display."""
        return {
            "total_controls": len(self._nodes),
            "total_bundles": len(self._bundles),
            "total_questions": len(self._questions),
            "disciplines": list(self._caf.keys()),
            "bundles": {
                k: {"count": len(v), "controls": v}
                for k, v in self._bundles.items()
            },
            "signal_sharing": self.signal_sharing_analysis(
                list(self._nodes.keys())
            ),
        }
