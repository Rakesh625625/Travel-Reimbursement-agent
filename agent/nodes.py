"""
LangGraph Nodes for Travel Reimbursement Approval Agent.

Each node is a pure function: ClaimState → dict (partial state update).

Nodes:
  1. policy_retrieval_node   – Calls policy MCP tools to fetch per-diem limits & rules
  2. receipt_validation_node – Calls receipt MCP tools to validate all claim items
  3. approval_matrix_node    – Calls approval MCP tools for grade-based thresholds
  4. calculation_node        – Pure computation: approved / deducted / rejected amounts
  5. decision_node           – LLM-based final decision with structured output
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from typing import Any
from datetime import datetime

from langchain_core.messages import HumanMessage, SystemMessage
import yaml
import os

# Load prompts from external file
PROMPTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompt.yaml")
with open(PROMPTS_FILE, "r") as f:
    PROMPTS = yaml.safe_load(f)
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import ValidationError

from agent.state import ClaimState
from agent.output_schema import DecisionOutput, RejectedItem, DeductedItem
from agent.logger import logger
from config import (
    LLM_PROVIDER, LLM_MODEL,
    OPENAI_API_KEY, GOOGLE_API_KEY, ANTHROPIC_API_KEY,
)

# ── MCP tool imports (call as regular Python functions in stdio mode) ──────────
from mcp_servers.policy_server import (
    get_per_diem_limits,
    get_policy_rules,
    get_full_policy,
    get_ineligible_categories,
)
from mcp_servers.receipt_server import validate_receipts
from mcp_servers.approval_server import get_approval_threshold, check_escalation_needed


# ── LLM factory ───────────────────────────────────────────────────────────────
def _get_llm():
    provider = LLM_PROVIDER.lower()
    if provider == "google":
        return ChatGoogleGenerativeAI(
            model=LLM_MODEL,
            google_api_key=GOOGLE_API_KEY,
            temperature=0.0,
        )
    else:
        raise ValueError(f"Unsupported LLM_PROVIDER: {LLM_PROVIDER}")


# ─────────────────────────────────────────────────────────────────────────────
# NODE 1 — Policy Retrieval
# ─────────────────────────────────────────────────────────────────────────────
def policy_retrieval_node(state: ClaimState) -> dict:
    """
    Fetches policy rules and per-diem limits for the claim's city + trip type.
    Uses policy_server MCP tools directly.
    """
    claim_id = state.get("claim_id", "N/A")
    logger.info(f"Node: policy_retrieval_node | Claim: {claim_id} | Start")
    trace = list(state.get("audit_trace", []))
    trace.append(f"[{datetime.utcnow().isoformat()}Z] NODE: policy_retrieval_node started")

    city = state["trip_city"]
    trip_type = state["trip_type"]

    # Per-diem limits for the trip city
    per_diem = get_per_diem_limits(city=city, trip_type=trip_type)
    trace.append(f"  → Per-diem limits fetched for '{city}' ({trip_type}): {per_diem}")

    # Policy rules per category
    categories_to_check = list({item["type"] for item in state["claim_items"]})
    policy_rules = {}
    for cat in categories_to_check:
        policy_rules[cat] = get_policy_rules(expense_type=cat, city=city, trip_type=trip_type)
    trace.append(f"  → Policy rules fetched for categories: {categories_to_check}")

    # Full policy text for LLM context
    full_policy = get_full_policy(trip_type=trip_type)
    full_policy_text = full_policy["policy_text"] + "\n\nFAQ:\n" + full_policy.get("faq_text", "")
    trace.append("  → Full policy text loaded for LLM context")

    trace.append(f"[{datetime.utcnow().isoformat()}Z] NODE: policy_retrieval_node completed")

    return {
        "per_diem_limits": per_diem,
        "policy_rules": policy_rules,
        "full_policy_text": full_policy_text,
        "audit_trace": trace,
    }


# ─────────────────────────────────────────────────────────────────────────────
# NODE 2 — Receipt Validation
# ─────────────────────────────────────────────────────────────────────────────
def receipt_validation_node(state: ClaimState) -> dict:
    """
    Validates all claim items against receipt and eligibility rules.
    Calls receipt_server validate_receipts() tool.
    """
    claim_id = state.get("claim_id", "N/A")
    logger.info(f"Node: receipt_validation_node | Claim: {claim_id} | Start")
    trace = list(state.get("audit_trace", []))
    trace.append(f"[{datetime.utcnow().isoformat()}Z] NODE: receipt_validation_node started")

    result = validate_receipts(claim_items=state["claim_items"])

    trace.append(f"  → Validation summary: {result['summary']}")
    if result["requires_manual_review"]:
        for reason in result["manual_review_reasons"]:
            trace.append(f"  → Manual review flag: {reason}")

    missing_documents = []
    for item in result["missing_receipt_items"]:
        if item.get("action") == "REJECT":
            missing_documents.append(
                f"Receipt required for {item['type']} (₹{item['amount']:,.0f}) — item {item['item_id']}"
            )

    trace.append(f"[{datetime.utcnow().isoformat()}Z] NODE: receipt_validation_node completed")

    return {
        "valid_items": result["valid_items"],
        "missing_receipt_items": result["missing_receipt_items"],
        "ineligible_items": result["ineligible_items"],
        "ambiguous_items": result["ambiguous_items"],
        "missing_documents": missing_documents,
        "requires_manual_review": result["requires_manual_review"],
        "manual_review_reasons": result["manual_review_reasons"],
        "flags": [f"INELIGIBLE:{i['type']}" for i in result["ineligible_items"]]
                + [f"MISSING_RECEIPT:{i['type']}" for i in result["missing_receipt_items"]
                   if i.get("action") == "REJECT"]
                + [f"AMBIGUOUS:{i['type']}" for i in result["ambiguous_items"]],
        "audit_trace": trace,
    }


# ─────────────────────────────────────────────────────────────────────────────
# NODE 3 — Approval Matrix
# ─────────────────────────────────────────────────────────────────────────────
def approval_matrix_node(state: ClaimState) -> dict:
    """
    Fetches grade-based approval thresholds and determines escalation level.
    """
    claim_id = state.get("claim_id", "N/A")
    logger.info(f"Node: approval_matrix_node | Claim: {claim_id} | Start")
    trace = list(state.get("audit_trace", []))
    trace.append(f"[{datetime.utcnow().isoformat()}Z] NODE: approval_matrix_node started")

    grade = state["employee_grade"]
    total = state["total_claimed"]

    thresholds = get_approval_threshold(employee_grade=grade)
    escalation = check_escalation_needed(total_amount=total, employee_grade=grade)

    trace.append(f"  → Grade '{grade}': self={thresholds['self_approve_limit']}, "
                 f"manager={thresholds['manager_approval_limit']}, "
                 f"finance={thresholds['finance_approval_limit']}")
    trace.append(f"  → Escalation level: {escalation['escalation_level']} — {escalation['reason']}")

    # If escalation requires manual review, merge with existing manual_review_reasons
    manual_review_reasons = list(state.get("manual_review_reasons", []))
    requires_manual_review = state.get("requires_manual_review", False)

    if escalation.get("requires_manual_review"):
        requires_manual_review = True
        manual_review_reasons.append(
            f"Escalation required: {escalation['escalation_level'].upper()} — {escalation['reason']}"
        )

    trace.append(f"[{datetime.utcnow().isoformat()}Z] NODE: approval_matrix_node completed")

    return {
        "approval_thresholds": thresholds,
        "escalation_result": escalation,
        "requires_manual_review": requires_manual_review,
        "manual_review_reasons": manual_review_reasons,
        "audit_trace": trace,
    }


# ─────────────────────────────────────────────────────────────────────────────
# NODE 4 — Calculation
# ─────────────────────────────────────────────────────────────────────────────
def calculation_node(state: ClaimState) -> dict:
    """
    Pure computation node: classifies items into approved/deducted/rejected
    and calculates final amounts based on policy limits.
    No LLM calls — deterministic rule engine.
    """
    claim_id = state.get("claim_id", "N/A")
    logger.info(f"Node: calculation_node | Claim: {claim_id} | Start")
    trace = list(state.get("audit_trace", []))
    trace.append(f"[{datetime.utcnow().isoformat()}Z] NODE: calculation_node started")

    per_diem = state["per_diem_limits"]
    policy_rules = state["policy_rules"]

    approved_items = []
    deducted_items = []
    rejected_items = []

    approved_amount = 0.0
    deducted_amount = 0.0
    rejected_amount = 0.0

    # Map categories to their per-diem limits
    limit_map = {
        "hotel": per_diem.get("hotel_per_night"),
        "meal": per_diem.get("meal_per_day"),
        "taxi": per_diem.get("taxi_per_day"),
        "flight": per_diem.get("flight_max_one_way"),
        "local_transport": per_diem.get("local_transport_per_day"),
    }

    # ── 1. Ineligible items → fully rejected ──────────────────────────────────
    for item in state.get("ineligible_items", []):
        rejected_items.append(RejectedItem(
            item_id=item["item_id"],
            type=item["type"],
            amount=item["amount"],
            reason=item["reason"],
            policy_reference=item.get("policy_reference", "Policy Section 3")
        ).model_dump())
        rejected_amount += item["amount"]
        trace.append(f"  → REJECT (ineligible): {item['type']} ₹{item['amount']}")

    # ── 2. Missing receipt items → partially/fully rejected ───────────────────
    for item in state.get("missing_receipt_items", []):
        reimbursable = item.get("reimbursable_amount", 0)
        deduction = item.get("deduction", item["amount"])

        if item.get("action") == "PARTIAL_APPROVE" and reimbursable > 0:
            deducted_items.append(DeductedItem(
                item_id=item["item_id"],
                type=item["type"],
                claimed_amount=item["amount"],
                approved_amount=reimbursable,
                deduction=deduction,
                reason=item["reason"],
                policy_reference=item.get("policy_reference", "Policy Section 5")
            ).model_dump())
            approved_amount += reimbursable
            deducted_amount += deduction
            trace.append(f"  → PARTIAL_APPROVE (missing receipt): {item['type']} "
                         f"₹{item['amount']} → approved ₹{reimbursable}")
        else:
            rejected_items.append(RejectedItem(
                item_id=item["item_id"],
                type=item["type"],
                amount=item["amount"],
                reason=item["reason"],
                policy_reference=item.get("policy_reference", "Policy Section 5")
            ).model_dump())
            rejected_amount += item["amount"]
            trace.append(f"  → REJECT (missing receipt): {item['type']} ₹{item['amount']}")

    # ── 3. Ambiguous items → manual review (treated as pending) ───────────────
    for item in state.get("ambiguous_items", []):
        # Flag for manual review; don't count in approved/rejected
        trace.append(f"  → PENDING_MANUAL_REVIEW (ambiguous): {item['type']} ₹{item['amount']}")

    # ── 4. Valid items → check against per-diem limits ────────────────────────
    for item in state.get("valid_items", []):
        cat = item["type"]
        amount = item["amount"]
        limit = limit_map.get(cat)

        # Categories with no per-diem cap (visa, conference, travel_insurance)
        if limit is None or cat in ("conference", "visa", "travel_insurance"):
            approved_items.append({**item, "approved_amount": amount})
            approved_amount += amount
            trace.append(f"  → APPROVE (no cap): {cat} ₹{amount}")
            continue

        # Limits are per-night or per-day; multiply by quantity
        qty = next(
            (raw["quantity"] for raw in state.get("claim_items", [])
             if raw.get("item_id") == item["item_id"]), 1
        )
        
        # Apply quantity to appropriate categories
        if cat in ("hotel", "meal", "taxi", "local_transport"):
            effective_limit = limit * qty
        else:
            effective_limit = limit

        if amount <= effective_limit:
            approved_items.append({**item, "approved_amount": amount})
            approved_amount += amount
            trace.append(f"  → APPROVE: {cat} ₹{amount} ≤ limit ₹{effective_limit}")
        else:
            # Amount exceeds limit — cap at limit
            deducted_items.append(DeductedItem(
                item_id=item["item_id"],
                type=cat,
                claimed_amount=amount,
                approved_amount=effective_limit,
                deduction=round(amount - effective_limit, 2),
                reason=f"Amount ₹{amount:,.0f} exceeds per-diem limit ₹{effective_limit:,.0f} for {cat}.",
                policy_reference=policy_rules.get(cat, {}).get("policy_reference", "Policy Section 7")
            ).model_dump())
            approved_amount += effective_limit
            deducted_amount += round(amount - effective_limit, 2)
            trace.append(f"  → PARTIAL_APPROVE (over limit): {cat} ₹{amount} → capped at ₹{effective_limit}")

    trace.append(
        f"  → Totals: approved=₹{approved_amount:.2f}, "
        f"deducted=₹{deducted_amount:.2f}, rejected=₹{rejected_amount:.2f}"
    )
    trace.append(f"[{datetime.utcnow().isoformat()}Z] NODE: calculation_node completed")

    return {
        "approved_items": approved_items,
        "deducted_items": deducted_items,
        "rejected_items": rejected_items,
        "approved_amount": round(approved_amount, 2),
        "deducted_amount": round(deducted_amount, 2),
        "rejected_amount": round(rejected_amount, 2),
        "audit_trace": trace,
    }


# ─────────────────────────────────────────────────────────────────────────────
# NODE 5 — Decision (LLM-Based)
# ─────────────────────────────────────────────────────────────────────────────
def decision_node(state: ClaimState) -> dict:
    """
    LLM-based final decision node.
    Generates structured DecisionOutput using the full policy context.
    """
    claim_id = state.get("claim_id", "N/A")
    logger.info(f"Node: decision_node | Claim: {claim_id} | Start")
    trace = list(state.get("audit_trace", []))
    trace.append(f"[{datetime.utcnow().isoformat()}Z] NODE: decision_node started")

    llm = _get_llm()

    # ── Determine overall decision ────────────────────────────────────────────
    approved_amount = state.get("approved_amount", 0.0)
    total_claimed = state.get("total_claimed", 0.0)
    requires_manual_review = state.get("requires_manual_review", False)
    rejected_items = state.get("rejected_items", [])
    deducted_items = state.get("deducted_items", [])
    ambiguous_items = state.get("ambiguous_items", [])

    if requires_manual_review or ambiguous_items:
        preliminary_decision = "Manual Review"
    elif rejected_items and not deducted_items and approved_amount == 0:
        preliminary_decision = "Reject"
    elif deducted_items or rejected_items or approved_amount < total_claimed:
        preliminary_decision = "Partially Approve"
    else:
        preliminary_decision = "Approve"

    # ── Policy references ─────────────────────────────────────────────────────
    policy_refs = set()
    for item in rejected_items:
        if isinstance(item, dict):
            policy_refs.add(item.get("policy_reference", ""))
    for item in deducted_items:
        if isinstance(item, dict):
            policy_refs.add(item.get("policy_reference", ""))
    policy_refs.discard("")

    # Escalation policy ref
    escalation = state.get("escalation_result", {})
    if escalation:
        policy_refs.add(escalation.get("policy_reference", "Policy Section 6"))

    # ── Build LLM prompt for explanation ─────────────────────────────────────
    system_prompt = PROMPTS.get("decision_node_system", {}).get("v1", "You are an expert travel reimbursement approver.")

    context = f"""
CLAIM SUMMARY:
- Claim ID: {state['claim_id']}
- Employee: {state['employee_name']} ({state['employee_grade']})
- Trip: {state['trip_city']}, {state['trip_country']} ({state['trip_type']})
- Purpose: {state['trip_purpose']}
- Total Claimed: ₹{total_claimed:,.2f}
- Approved Amount: ₹{approved_amount:,.2f}
- Deducted Amount: ₹{state.get('deducted_amount', 0):,.2f}
- Rejected Amount: ₹{state.get('rejected_amount', 0):,.2f}
- Decision: {preliminary_decision}
- Requires Manual Review: {requires_manual_review}

REJECTED ITEMS ({len(rejected_items)} items):
{json.dumps(rejected_items, indent=2) if rejected_items else "None"}

DEDUCTED ITEMS ({len(deducted_items)} items):
{json.dumps(deducted_items, indent=2) if deducted_items else "None"}

APPROVED ITEMS ({len(state.get('approved_items', []))} items):
{json.dumps(state.get('approved_items', []), indent=2) if state.get('approved_items') else "None"}

MANUAL REVIEW REASONS:
{chr(10).join(state.get('manual_review_reasons', [])) or "None"}

ESCALATION:
{json.dumps(escalation, indent=2) if escalation else "None"}

Write a 2-3 sentence explanation of this decision for the employee and approver.
"""

    messages = [SystemMessage(content=system_prompt), HumanMessage(content=context)]
    response = llm.invoke(messages)
    explanation = response.content.strip()

    trace.append(f"  → LLM generated explanation ({len(explanation)} chars)")

    # ── Determine confidence ──────────────────────────────────────────────────
    if requires_manual_review:
        confidence = "Low"
    elif deducted_items and not rejected_items:
        confidence = "High"
    elif deducted_items or rejected_items:
        confidence = "Medium"
    else:
        confidence = "High"

    # ── Build final DecisionOutput ────────────────────────────────────────────
    escalation_level = escalation.get("escalation_level", "none") if escalation else "none"
    escalation_reason = escalation.get("reason") if escalation.get("escalation_needed") else None

    try:
        output = DecisionOutput(
            claim_id=state["claim_id"],
            employee_id=state["employee_id"],
            employee_name=state["employee_name"],
            decision=preliminary_decision,
            confidence=confidence,
            total_claimed=total_claimed,
            approved_amount=approved_amount,
            deducted_amount=state.get("deducted_amount", 0.0),
            rejected_amount=state.get("rejected_amount", 0.0),
            approved_items=state.get("approved_items", []),
            deducted_items=[DeductedItem(**i) if isinstance(i, dict) else i
                            for i in deducted_items],
            rejected_items=[RejectedItem(**i) if isinstance(i, dict) else i
                            for i in rejected_items],
            missing_documents=state.get("missing_documents", []),
            policy_references=sorted(policy_refs),
            requires_manual_review=requires_manual_review,
            escalation_level=escalation_level if escalation_level != "none" else None,
            escalation_reason=escalation_reason,
            explanation=explanation,
            audit_trace=trace,
        )
    except (ValidationError, Exception) as e:
        trace.append(f"  → WARNING: DecisionOutput validation error: {e}")
        # Build a minimal valid output
        output = DecisionOutput(
            claim_id=state["claim_id"],
            employee_id=state["employee_id"],
            employee_name=state["employee_name"],
            decision="Manual Review",
            confidence="Low",
            total_claimed=total_claimed,
            approved_amount=approved_amount,
            deducted_amount=state.get("deducted_amount", 0.0),
            rejected_amount=state.get("rejected_amount", 0.0),
            missing_documents=state.get("missing_documents", []),
            policy_references=sorted(policy_refs),
            requires_manual_review=True,
            explanation=f"Decision could not be finalized due to a processing error. Manual review required. ({e})",
            audit_trace=trace,
        )

    trace.append(f"[{datetime.utcnow().isoformat()}Z] NODE: decision_node completed — {preliminary_decision}")

    return {
        "decision": output.decision,
        "confidence": output.confidence,
        "explanation": output.explanation,
        "policy_references": output.policy_references,
        "audit_trace": trace,
        "final_output": output.model_dump(),
        "messages": messages,
    }
