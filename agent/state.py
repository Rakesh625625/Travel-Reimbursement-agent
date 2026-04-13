"""
LangGraph State definition for the Travel Reimbursement Approval Agent.
This TypedDict holds all data as it flows through the graph nodes.
"""

from typing import TypedDict, List, Optional, Annotated
from langchain_core.messages import BaseMessage
import operator


class ClaimState(TypedDict):
    # ── Input Fields ──────────────────────────────────────────────────────────
    claim_id: str
    employee_id: str
    employee_name: str
    employee_grade: str           # L1, L2, L3, L4, L5, L6, L7
    department: str
    trip_city: str
    trip_country: str
    trip_type: str                # "domestic" | "international"
    trip_purpose: str
    travel_start_date: str
    travel_end_date: str
    submission_date: str
    claim_items: List[dict]       # Raw expense line items
    total_claimed: float
    manager_id: str
    notes: str

    # ── Filled by policy_retrieval_node ───────────────────────────────────────
    per_diem_limits: dict         # City-wise limits from policy_server
    policy_rules: dict            # Rules per category
    full_policy_text: str         # Full policy text for LLM context

    # ── Filled by receipt_validation_node ─────────────────────────────────────
    valid_items: List[dict]       # Items with valid receipts
    missing_receipt_items: List[dict]
    ineligible_items: List[dict]
    ambiguous_items: List[dict]
    missing_documents: List[str]

    # ── Filled by approval_matrix_node ────────────────────────────────────────
    approval_thresholds: dict     # Grade-based limits
    escalation_result: dict       # Escalation decision

    # ── Filled by calculation_node ────────────────────────────────────────────
    approved_items: List[dict]
    deducted_items: List[dict]
    rejected_items: List[dict]
    approved_amount: float
    deducted_amount: float
    rejected_amount: float

    # ── Routing Flags ─────────────────────────────────────────────────────────
    requires_manual_review: bool
    manual_review_reasons: List[str]
    safety_violation: bool        # Flagged by input_guardrail
    safety_notes: str             # Details on why it was flagged
    flags: List[str]              # Any anomaly or warning flags

    # ── LangChain Messages (for LLM calls) ────────────────────────────────────
    messages: Annotated[List[BaseMessage], operator.add]

    # ── Final Output ──────────────────────────────────────────────────────────
    decision: str                 # Approve | Partially Approve | Reject | Manual Review
    confidence: str               # High | Medium | Low
    explanation: str
    policy_references: List[str]
    audit_trace: List[str]
    final_output: dict            # Serialized DecisionOutput
