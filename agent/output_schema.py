"""
Pydantic output schema for structured decision output.
This ensures the LLM always returns consistent, business-usable JSON.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from datetime import datetime


class RejectedItem(BaseModel):
    item_id: str
    type: str
    amount: float
    reason: str
    policy_reference: str


class DeductedItem(BaseModel):
    item_id: str
    type: str
    claimed_amount: float
    approved_amount: float
    deduction: float
    reason: str
    policy_reference: str


class DecisionOutput(BaseModel):
    """Structured reimbursement decision output."""

    claim_id: str = Field(description="Unique claim identifier")
    employee_id: str = Field(description="Employee ID")
    employee_name: str = Field(description="Employee full name")

    decision: Literal["Approve", "Partially Approve", "Reject", "Manual Review"] = Field(
        description="Final reimbursement decision"
    )
    confidence: Literal["High", "Medium", "Low"] = Field(
        description="Confidence level in the decision"
    )

    total_claimed: float = Field(description="Total amount claimed by employee")
    approved_amount: float = Field(description="Total amount approved for reimbursement")
    deducted_amount: float = Field(description="Total amount deducted from claim")
    rejected_amount: float = Field(description="Total amount fully rejected")

    approved_items: List[dict] = Field(default_factory=list, description="Fully approved line items")
    deducted_items: List[DeductedItem] = Field(default_factory=list, description="Partially approved items with deductions")
    rejected_items: List[RejectedItem] = Field(default_factory=list, description="Fully rejected line items")

    missing_documents: List[str] = Field(default_factory=list, description="List of missing receipts or documents")
    policy_references: List[str] = Field(default_factory=list, description="Policy clauses cited in this decision")

    requires_manual_review: bool = Field(description="Whether human review is required")
    escalation_level: Optional[str] = Field(None, description="Escalation level: manager/finance/cfo/none")
    escalation_reason: Optional[str] = Field(None, description="Why escalation is required")

    explanation: str = Field(description="2-3 sentence business-clear explanation of the decision")
    safety_check: str = Field("Passed", description="Result of guardrail validation: Passed | Flagged | Blocked")
    audit_trace: List[str] = Field(default_factory=list, description="Step-by-step agent execution log")

    processed_at: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat() + "Z",
        description="ISO timestamp of when decision was made"
    )
