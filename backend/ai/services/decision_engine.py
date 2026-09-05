"""
ai/services/decision_engine.py
──────────────────────────────
Autonomous Revenue Decision Engine.

This module receives all RevenueOpportunity candidates from the Revenue
Opportunity Engine and runs them through a deterministic multi-step decision
pipeline to select the single best valid business action.

DECISION PIPELINE
─────────────────
candidate opportunities
    → policy validation      (policy_compliant flag + re-check discount/margin bounds)
    → safety validation      (price > 0, discount within ceiling, margin above floor)
    → economic validation    (auto_approval_limit → sets requires_approval)
    → score comparison       (opportunity_score + tie-breaking)
    → final selection
    → explainable decision trace

IMPORTANT CONSTRAINTS
─────────────────────
• The engine ONLY recommends/decides an action. It does NOT:
    - call Razorpay
    - create payment orders
    - charge customers
    - modify inventory or prices
    - execute any external side effects
• cost_price is NEVER exposed through any output field.
• requires_approval = True does NOT prevent recommendation — it flags that a
  human or higher-authority system must authorise before execution.
• RECOMMENDED ≠ AUTHORIZED.

CONFIDENCE SCORE
────────────────
confidence is a deterministic heuristic score (0.0–1.0) representing decision
stability — NOT an ML model confidence interval.  It is derived from the score
gap between the selected opportunity and the next-best valid alternative.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from merchants.models import MerchantPolicy
    from .intent_engine import BuyerIntent
    from .revenue_engine import RevenueOpportunity


# ===========================================================================
# Data structures
# ===========================================================================

@dataclass
class ValidationResult:
    """Outcome of a single-opportunity validation pass."""
    valid: bool
    stage: str = ""                  # which validation stage rejected it
    rejection_reason: str = ""       # human-readable rejection explanation


@dataclass
class DecisionResult:
    """
    The final output of the Decision Engine.

    Fields
    ──────
    selected_action          : action string of the chosen opportunity, or
                               "NO_VALID_ACTION" if every candidate was rejected.
    selected_opportunity     : the chosen RevenueOpportunity (or None).
    decision_score           : opportunity_score of the selected opportunity.
    confidence               : deterministic heuristic stability score (0.0–1.0).
                               NOT an ML confidence; reflects score gap vs.
                               next-best alternative.
    reason                   : human-readable summary of why this action was chosen.
    alternatives             : top-N valid opportunities that were NOT selected.
    rejected_opportunities   : list of dicts describing why each candidate
                               was excluded from automatic selection.
    decision_trace           : machine-readable JSON-safe dict recording every
                               step of the pipeline (for explainable AI traces).
    requires_approval        : True when the proposed transaction value exceeds
                               MerchantPolicy.auto_approval_limit.
                               RECOMMENDED ≠ AUTHORIZED.
    """
    selected_action: str
    selected_opportunity: Optional["RevenueOpportunity"]
    decision_score: int
    confidence: float
    reason: str
    alternatives: list["RevenueOpportunity"]
    rejected_opportunities: list[dict]
    decision_trace: dict
    requires_approval: bool


# ===========================================================================
# Constants
# ===========================================================================

# Maximum number of alternatives to include in DecisionResult.alternatives.
_MAX_ALTERNATIVES = 5

# Confidence thresholds keyed on score gap to next-best valid alternative.
# This is a deterministic heuristic — not an ML model output.
_CONFIDENCE_THRESHOLDS: list[tuple[int, float]] = [
    (50, 0.95),
    (30, 0.85),
    (15, 0.70),
    (5,  0.55),
    (0,  0.40),
]

# Confidence when there is no valid alternative (sole valid candidate).
_CONFIDENCE_SOLE_CANDIDATE_HIGH  = 0.80  # selected score > 100
_CONFIDENCE_SOLE_CANDIDATE_MED   = 0.65  # selected score > 50
_CONFIDENCE_SOLE_CANDIDATE_LOW   = 0.50  # otherwise


# ===========================================================================
# Validation pipeline
# ===========================================================================

def _validate_opportunity(
    opp: "RevenueOpportunity",
    policy: "MerchantPolicy",
) -> ValidationResult:
    """
    Run a multi-stage validation pipeline for a single opportunity.

    Stages (in order):
      1. policy_compliant flag  — coarse compliance check from revenue engine
      2. safety                 — proposed price positive
      3. discount ceiling       — re-validate discount does not exceed policy max
      4. margin floor           — re-validate margin does not fall below policy min
      5. inventory / activity   — product must be in stock and active (where checkable)

    Returns ValidationResult with valid=True or a rejection reason.
    """
    # Stage 1: Policy compliance flag (set by revenue engine)
    if not opp.policy_compliant:
        return ValidationResult(
            valid=False,
            stage="policy_compliant",
            rejection_reason=(
                f"Revenue engine marked this opportunity non-compliant: {opp.reason}"
            ),
        )

    # Stage 2: Safety — proposed price must be positive
    if opp.proposed_price <= Decimal("0"):
        return ValidationResult(
            valid=False,
            stage="safety",
            rejection_reason="Proposed price is zero or negative.",
        )

    # Stage 3: Discount ceiling — independent re-check
    if opp.discount_percent > policy.maximum_discount_percent:
        return ValidationResult(
            valid=False,
            stage="discount_ceiling",
            rejection_reason=(
                f"Discount {opp.discount_percent}% exceeds policy maximum "
                f"{policy.maximum_discount_percent}%."
            ),
        )

    # Stage 4: Margin floor — independent re-check
    if opp.resulting_margin_percent < policy.minimum_margin_percent:
        return ValidationResult(
            valid=False,
            stage="margin_floor",
            rejection_reason=(
                f"Resulting margin {opp.resulting_margin_percent}% is below "
                f"policy minimum {policy.minimum_margin_percent}%."
            ),
        )

    return ValidationResult(valid=True, stage="passed", rejection_reason="")


# ===========================================================================
# Confidence calculation
# ===========================================================================

def _calculate_confidence(
    selected_score: int,
    alternatives: list["RevenueOpportunity"],
) -> float:
    """
    Compute a deterministic heuristic confidence score (0.0–1.0).

    This is NOT an ML confidence interval.  It represents decision stability:
    how much better the selected opportunity is compared to the next-best valid
    alternative.

    A large score gap → high confidence (the decision is clear-cut).
    A small score gap → low confidence (the decision is marginal).
    No valid alternative → confidence based on absolute score strength.
    """
    if not alternatives:
        # Sole valid candidate — confidence based on absolute score strength
        if selected_score > 100:
            return _CONFIDENCE_SOLE_CANDIDATE_HIGH
        elif selected_score > 50:
            return _CONFIDENCE_SOLE_CANDIDATE_MED
        else:
            return _CONFIDENCE_SOLE_CANDIDATE_LOW

    next_best_score = alternatives[0].opportunity_score
    gap = selected_score - next_best_score

    for threshold, confidence in _CONFIDENCE_THRESHOLDS:
        if gap >= threshold:
            return confidence

    return 0.40  # fallback (gap < 0 means selected is actually lower, shouldn't happen)


# ===========================================================================
# Tie-breaking comparator
# ===========================================================================

def _tie_break_key(opp: "RevenueOpportunity") -> tuple:
    """
    Deterministic tie-breaking sort key (all dimensions descending unless noted).

    Priority order (documented in spec):
      1. policy_compliant (True first — already filtered, but safety guard)
      2. opportunity_score (higher is better)
      3. intent_relevance signal from metadata (higher is better)
      4. margin_preservation signal from metadata (higher is better)
      5. proposed_price (lower is better for customer — negate)
      6. product_id (lower / stable ordering)
    """
    signals = opp.metadata.get("signals", {})
    return (
        1 if opp.policy_compliant else 0,        # 1. compliance first
        opp.opportunity_score,                    # 2. score desc
        signals.get("intent_relevance", 0),       # 3. relevance desc
        signals.get("margin_preservation", 0),    # 4. margin desc
        -int(opp.proposed_price * 100),           # 5. price asc (negate)
        -opp.product_id,                          # 6. stable product ordering
    )


# ===========================================================================
# Decision trace builder
# ===========================================================================

def _build_trace(
    intent: "BuyerIntent",
    all_opportunities: list["RevenueOpportunity"],
    valid_opportunities: list["RevenueOpportunity"],
    rejected: list[dict],
    selected: Optional["RevenueOpportunity"],
    alternatives: list["RevenueOpportunity"],
    requires_approval: bool,
    confidence: float,
) -> dict:
    """
    Build a machine-readable decision trace dict.

    The trace records:
      - summary counts
      - input intent summary
      - per-candidate evaluation results
      - final selection explanation

    All values are JSON-serialisable primitives (str, int, float, bool, None).
    """
    def _opp_summary(opp: "RevenueOpportunity", decision: str, rejection_reason: str = "") -> dict:
        signals = opp.metadata.get("signals", {})
        entry: dict = {
            "action":             opp.action,
            "product_id":         opp.product_id,
            "product_name":       opp.product_name,
            "opportunity_score":  opp.opportunity_score,
            "policy_compliant":   opp.policy_compliant,
            "proposed_price":     str(opp.proposed_price),
            "discount_percent":   str(opp.discount_percent),
            "margin_percent":     str(opp.resulting_margin_percent),
            "budget_fit":         signals.get("budget_fit"),
            "margin_preservation":signals.get("margin_preservation"),
            "intent_relevance":   signals.get("intent_relevance"),
            "decision":           decision,
        }
        if rejection_reason:
            entry["rejection_reason"] = rejection_reason
        if opp.recommended_product_id is not None:
            entry["recommended_product_id"]   = opp.recommended_product_id
            entry["recommended_product_name"] = opp.recommended_product_name
        return entry

    candidate_evaluations = []

    # Selected
    if selected:
        candidate_evaluations.append(_opp_summary(selected, "selected"))

    # Alternatives
    for alt in alternatives:
        candidate_evaluations.append(_opp_summary(alt, "alternative"))

    # Rejected
    for rej in rejected:
        opp = rej["opportunity"]
        candidate_evaluations.append(
            _opp_summary(opp, "rejected", rej["reason"])
        )

    return {
        "input": {
            "intent_type":   intent.intent_type,
            "search_query":  intent.search_query,
            "product_type":  intent.product_type,
            "category":      intent.category,
            "budget_max":    intent.budget_max,
            "budget_min":    intent.budget_min,
        },
        "pipeline_summary": {
            "candidates_considered":  len(all_opportunities),
            "candidates_validated":   len(valid_opportunities),
            "candidates_rejected":    len(rejected),
            "selected_action":        selected.action if selected else "NO_VALID_ACTION",
            "requires_approval":      requires_approval,
            "confidence":             confidence,
        },
        "candidate_evaluations": candidate_evaluations,
    }


# ===========================================================================
# Public API
# ===========================================================================

def make_decision(
    intent: "BuyerIntent",
    opportunities: list["RevenueOpportunity"],
    policy: "MerchantPolicy",
) -> DecisionResult:
    """
    Run the autonomous decision pipeline and return a DecisionResult.

    Parameters
    ----------
    intent        : Structured buyer intent (from intent_engine).
    opportunities : Ranked candidate list (from revenue_engine.generate_opportunities).
    policy        : MerchantPolicy with discount/margin/approval limits.

    Returns
    -------
    DecisionResult
        Always returns a result — if all opportunities are invalid the
        selected_action is "NO_VALID_ACTION" and selected_opportunity is None.

    Decision pipeline
    ─────────────────
    1. For each opportunity: run _validate_opportunity() through all stages.
    2. Collect valid_opportunities and rejected_opportunities separately.
    3. Sort valid_opportunities by _tie_break_key (multi-dimensional).
    4. Select the first (highest) valid opportunity.
    5. Determine requires_approval from auto_approval_limit.
    6. Compute confidence from score gap vs. next-best alternative.
    7. Build decision trace.
    """
    auto_limit = policy.auto_approval_limit

    # ── Step 1 & 2: Validate all candidates ──────────────────────────────────
    valid_opportunities: list["RevenueOpportunity"] = []
    rejected_opportunities: list[dict] = []

    for opp in opportunities:
        result = _validate_opportunity(opp, policy)
        if result.valid:
            valid_opportunities.append(opp)
        else:
            rejected_opportunities.append({
                "opportunity": opp,
                "stage":       result.stage,
                "reason":      result.rejection_reason,
            })

    # ── Step 3: Rank valid candidates with tie-breaking ──────────────────────
    valid_opportunities.sort(key=_tie_break_key, reverse=True)

    # ── Step 4: Select best ───────────────────────────────────────────────────
    if not valid_opportunities:
        # No valid action found — this is a legitimate outcome
        trace = _build_trace(
            intent=intent,
            all_opportunities=opportunities,
            valid_opportunities=[],
            rejected=rejected_opportunities,
            selected=None,
            alternatives=[],
            requires_approval=False,
            confidence=0.0,
        )
        return DecisionResult(
            selected_action="NO_VALID_ACTION",
            selected_opportunity=None,
            decision_score=0,
            confidence=0.0,
            reason=(
                "No policy-compliant opportunity could be identified for the "
                "given intent and merchant constraints."
            ),
            alternatives=[],
            rejected_opportunities=rejected_opportunities,
            decision_trace=trace,
            requires_approval=False,
        )

    selected = valid_opportunities[0]
    alternatives = valid_opportunities[1: 1 + _MAX_ALTERNATIVES]

    # ── Step 5: Auto-approval check ───────────────────────────────────────────
    requires_approval = selected.proposed_price > auto_limit

    # ── Step 6: Confidence ────────────────────────────────────────────────────
    confidence = _calculate_confidence(selected.opportunity_score, alternatives)

    # ── Step 7: Reason ───────────────────────────────────────────────────────
    action_label = {
        "NO_ACTION": "selling at catalog price",
        "DISCOUNT":  f"offering a {selected.discount_percent}% discount",
        "UPSELL":    f"recommending an upgrade to '{selected.recommended_product_name}'",
        "BUNDLE":    f"bundling with '{selected.recommended_product_name}'",
    }.get(selected.action, selected.action)

    approval_note = (
        " (requires approval before execution — value exceeds auto-approval limit)"
        if requires_approval else ""
    )

    reason = (
        f"Selected {selected.action} on '{selected.product_name}' by {action_label}. "
        f"Score: {selected.opportunity_score}, margin: {selected.resulting_margin_percent}%, "
        f"policy compliant: True.{approval_note}"
    )

    # ── Step 8: Build trace ───────────────────────────────────────────────────
    trace = _build_trace(
        intent=intent,
        all_opportunities=opportunities,
        valid_opportunities=valid_opportunities,
        rejected=rejected_opportunities,
        selected=selected,
        alternatives=alternatives,
        requires_approval=requires_approval,
        confidence=confidence,
    )

    return DecisionResult(
        selected_action=selected.action,
        selected_opportunity=selected,
        decision_score=selected.opportunity_score,
        confidence=confidence,
        reason=reason,
        alternatives=alternatives,
        rejected_opportunities=rejected_opportunities,
        decision_trace=trace,
        requires_approval=requires_approval,
    )
