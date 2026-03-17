"""
Aggregator — four strategies for combining council member evaluations into a final verdict.

Strategies:
  weighted_average  — score × metric_weight × member_confidence × tier_weight
  borda_count       — rank-based points, robust to score outliers
  majority          — each member votes for their top-1 plan
  veto              — any member can block a plan; remainder go to weighted_average
"""

import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class Aggregator:

    STRATEGIES = ["weighted_average", "borda_count", "majority", "veto"]

    # ─────────────────────────────────────────────────────────────────────────
    # Main entry point
    # ─────────────────────────────────────────────────────────────────────────

    def aggregate(
        self,
        strategy: str,
        council_evaluations: Dict[str, Dict[str, Any]],
        plan_labels: List[str],
        metrics: List[Dict[str, Any]],
        tier_weights: Dict[int, float]
    ) -> Dict[str, Any]:
        """
        Returns:
          {
            strategy, plan_scores, ranking, winner,
            inter_council_agreement, vetoed_plans, details
          }
        """
        # Filter to successful evaluations only
        successful = {
            label: ev for label, ev in council_evaluations.items()
            if ev.get("_status") == "success"
        }

        if not successful:
            logger.warning("No successful council evaluations — cannot aggregate")
            return {
                "strategy": strategy,
                "plan_scores": {p: 0.0 for p in plan_labels},
                "ranking": plan_labels,
                "winner": plan_labels[0] if plan_labels else None,
                "inter_council_agreement": 0.0,
                "vetoed_plans": [],
                "details": {},
                "error": "no_successful_evaluations"
            }

        if strategy not in self.STRATEGIES:
            logger.warning(f"Unknown strategy '{strategy}', falling back to borda_count")
            strategy = "borda_count"

        metric_map = {m["name"]: m["weight"] for m in metrics}

        if strategy == "weighted_average":
            scores, details = self._weighted_average(successful, plan_labels, metric_map, tier_weights)
            vetoed = []
        elif strategy == "borda_count":
            scores, details = self._borda_count(successful, plan_labels, tier_weights)
            vetoed = []
        elif strategy == "majority":
            scores, details = self._majority(successful, plan_labels)
            vetoed = []
        elif strategy == "veto":
            vetoed, scores, details = self._veto(
                successful, plan_labels, metric_map, tier_weights,
                veto_min_members=1
            )

        ranking = sorted(scores.keys(), key=lambda p: scores[p], reverse=True)
        winner = ranking[0] if ranking else None
        agreement = self._compute_agreement(successful, plan_labels)

        return {
            "strategy": strategy,
            "plan_scores": scores,
            "ranking": ranking,
            "winner": winner,
            "inter_council_agreement": round(agreement, 3),
            "vetoed_plans": vetoed,
            "details": details
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Strategy 1: Weighted Average
    # ─────────────────────────────────────────────────────────────────────────

    def _weighted_average(
        self,
        evals: Dict[str, Dict],
        plan_labels: List[str],
        metric_map: Dict[str, float],
        tier_weights: Dict[int, float]
    ):
        """
        plan_score = Σ(metric_score × metric_weight × confidence × tier_weight)
                     / Σ(metric_weight)
        """
        totals = {p: 0.0 for p in plan_labels}
        weight_sums = {p: 0.0 for p in plan_labels}
        details = {}

        for member_label, ev in evals.items():
            tier = ev.get("_tier", 2)
            tw = tier_weights.get(tier, 0.75)
            confidence = ev.get("confidence", 0.5)
            member_scores = ev.get("scores", {})
            details[member_label] = {}

            for plan in plan_labels:
                plan_scores = member_scores.get(plan, {})
                plan_total = 0.0
                plan_weight = 0.0
                for metric_name, mw in metric_map.items():
                    score = float(plan_scores.get(metric_name, 0.0))
                    effective_weight = mw * confidence * tw
                    plan_total += score * effective_weight
                    plan_weight += effective_weight
                if plan_weight > 0:
                    totals[plan] += plan_total
                    weight_sums[plan] += plan_weight
                details[member_label][plan] = round(plan_total / plan_weight, 4) if plan_weight > 0 else 0.0

        final_scores = {
            p: round(totals[p] / weight_sums[p], 4) if weight_sums[p] > 0 else 0.0
            for p in plan_labels
        }
        return final_scores, details

    # ─────────────────────────────────────────────────────────────────────────
    # Strategy 2: Borda Count
    # ─────────────────────────────────────────────────────────────────────────

    def _borda_count(
        self,
        evals: Dict[str, Dict],
        plan_labels: List[str],
        tier_weights: Dict[int, float]
    ):
        """
        Each member assigns N points to 1st, N-1 to 2nd, etc.
        Points weighted by tier_weight.
        """
        n = len(plan_labels)
        totals = {p: 0.0 for p in plan_labels}
        details = {}

        for member_label, ev in evals.items():
            tier = ev.get("_tier", 2)
            tw = tier_weights.get(tier, 0.75)
            ranking = ev.get("ranking", [])

            # Fill in any missing plans at the bottom
            ranked = list(ranking) + [p for p in plan_labels if p not in ranking]

            details[member_label] = {}
            for idx, plan in enumerate(ranked):
                if plan in plan_labels:
                    points = (n - idx) * tw
                    totals[plan] = totals.get(plan, 0.0) + points
                    details[member_label][plan] = round(points, 2)

        return {p: round(totals[p], 2) for p in plan_labels}, details

    # ─────────────────────────────────────────────────────────────────────────
    # Strategy 3: Majority Verdict
    # ─────────────────────────────────────────────────────────────────────────

    def _majority(
        self,
        evals: Dict[str, Dict],
        plan_labels: List[str]
    ):
        """Each member casts one vote for their top-ranked plan. Tie-break by count."""
        votes = {p: 0 for p in plan_labels}
        details = {}

        for member_label, ev in evals.items():
            ranking = ev.get("ranking", [])
            top = ranking[0] if ranking else None
            if top and top in votes:
                votes[top] += 1
            details[member_label] = {"voted_for": top}

        return {p: float(votes[p]) for p in plan_labels}, details

    # ─────────────────────────────────────────────────────────────────────────
    # Strategy 4: Veto System
    # ─────────────────────────────────────────────────────────────────────────

    def _veto(
        self,
        evals: Dict[str, Dict],
        plan_labels: List[str],
        metric_map: Dict[str, float],
        tier_weights: Dict[int, float],
        veto_min_members: int = 1
    ):
        """
        Plans flagged by >= veto_min_members are eliminated.
        Remaining plans are ranked by weighted_average.
        If all plans are vetoed, the least-vetoed one survives with a warning.
        """
        veto_counts = {p: 0 for p in plan_labels}
        veto_reasons = {p: [] for p in plan_labels}
        details = {}

        for member_label, ev in evals.items():
            vetoes = ev.get("vetoes", [])
            details[member_label] = {"vetoed": [v["plan"] for v in vetoes if v.get("plan") in plan_labels]}
            for v in vetoes:
                plan = v.get("plan")
                if plan in veto_counts:
                    veto_counts[plan] += 1
                    veto_reasons[plan].append(
                        f"{member_label}: {v.get('reason', 'no reason given')}"
                    )

        vetoed = [p for p in plan_labels if veto_counts[p] >= veto_min_members]
        surviving = [p for p in plan_labels if p not in vetoed]

        if not surviving:
            # All vetoed — use least-vetoed
            surviving = [min(veto_counts, key=lambda p: veto_counts[p])]
            logger.warning(f"All plans vetoed — using least-vetoed: {surviving[0]}")

        scores, wa_details = self._weighted_average(evals, surviving, metric_map, tier_weights)
        details["veto_details"] = {
            "veto_counts": veto_counts,
            "veto_reasons": veto_reasons,
            "wa_details": wa_details
        }

        # Give eliminated plans score = -1 so they sort last
        for p in vetoed:
            scores[p] = -1.0

        return vetoed, scores, details

    # ─────────────────────────────────────────────────────────────────────────
    # Agreement metric
    # ─────────────────────────────────────────────────────────────────────────

    def _compute_agreement(
        self,
        evals: Dict[str, Dict],
        plan_labels: List[str]
    ) -> float:
        """
        Fraction of members that agree on the top-ranked plan.
        Returns 1.0 if all members pick the same winner, 0.0 if all differ.
        """
        top_picks = []
        for ev in evals.values():
            ranking = ev.get("ranking", [])
            if ranking:
                top_picks.append(ranking[0])

        if not top_picks:
            return 0.0

        most_common = max(set(top_picks), key=top_picks.count)
        return top_picks.count(most_common) / len(top_picks)
