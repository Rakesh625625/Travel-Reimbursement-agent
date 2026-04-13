"""
MCP Server 3: Approval Matrix Server
Determines approval thresholds and escalation requirements per employee grade.

Tools exposed:
  - get_approval_threshold(employee_grade)               -> self/manager/finance limits
  - check_escalation_needed(total_amount, employee_grade) -> escalation decision
  - get_all_grades()                                      -> full approval matrix
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from fastmcp import FastMCP
from config import APPROVAL_MATRIX_FILE
from agent.logger import logger

# ── Initialize MCP Server ────────────────────────────────────────────────────
mcp = FastMCP(
    name="approval-server",
    instructions="Provides employee grade-based approval thresholds and escalation logic for reimbursement claims."
)

# ── Load approval matrix ──────────────────────────────────────────────────────
def _load_matrix() -> pd.DataFrame:
    return pd.read_csv(APPROVAL_MATRIX_FILE)

# ── Tool 1: get_approval_threshold ────────────────────────────────────────────
@mcp.tool()
def get_approval_threshold(employee_grade: str) -> dict:
    """
    Returns the approval limits for a given employee grade.

    Args:
        employee_grade: Employee grade code (e.g., 'L1', 'L2', 'L3', 'L4', 'L5')

    Returns:
        dict with self_approve_limit, manager_approval_limit,
        finance_approval_limit, cfo_approval_limit, grade_label
    """
    df = _load_matrix()
    grade_upper = employee_grade.upper().strip()

    row = df[df["grade"].str.upper() == grade_upper]

    if row.empty:
        # Default to L1 (most restrictive) if grade not found
        default = df[df["grade"] == "L1"].iloc[0]
        return {
            "found": False,
            "grade": employee_grade,
            "grade_label": "Unknown — defaulting to L1 (Junior Associate)",
            "self_approve_limit": float(default["self_approve_limit"]),
            "manager_approval_limit": float(default["manager_approval_limit"]),
            "finance_approval_limit": float(default["finance_approval_limit"]),
            "cfo_approval_limit": float(default["cfo_approval_limit"]),
            "grade_not_found": True,
            "policy_reference": "FAQ Q4 – Unknown grade defaults to L1"
        }

    r = row.iloc[0]
    logger.info(f"MCP: get_approval_threshold | grade={employee_grade} | found=True")
    return {
        "found": True,
        "grade": r["grade"],
        "grade_label": r["grade_label"],
        "self_approve_limit": float(r["self_approve_limit"]),
        "manager_approval_limit": float(r["manager_approval_limit"]),
        "finance_approval_limit": float(r["finance_approval_limit"]),
        "cfo_approval_limit": float(r["cfo_approval_limit"]),
        "grade_not_found": False,
        "policy_reference": "Policy Section 6 – Approval Matrix"
    }

# ── Tool 2: check_escalation_needed ──────────────────────────────────────────
@mcp.tool()
def check_escalation_needed(total_amount: float, employee_grade: str) -> dict:
    """
    Determines whether a claim needs escalation based on amount and employee grade.

    Args:
        total_amount: Total reimbursable amount being claimed (INR)
        employee_grade: Employee grade code (e.g., 'L1', 'L2')

    Returns:
        dict with escalation_needed, escalation_level, approver, reason, policy_reference
    """
    thresholds = get_approval_threshold(employee_grade)

    self_limit = thresholds["self_approve_limit"]
    manager_limit = thresholds["manager_approval_limit"]
    finance_limit = thresholds["finance_approval_limit"]
    cfo_limit = thresholds["cfo_approval_limit"]
    grade_label = thresholds["grade_label"]

    if total_amount <= self_limit:
        return {
            "escalation_needed": False,
            "escalation_level": "none",
            "approver": "auto-approved",
            "total_amount": total_amount,
            "self_approve_limit": self_limit,
            "reason": f"Amount ₹{total_amount:,.0f} is within self-approval limit of ₹{self_limit:,.0f} for {grade_label}.",
            "policy_reference": "Policy Section 6 – Approval Matrix"
        }
    elif total_amount <= manager_limit:
        return {
            "escalation_needed": True,
            "escalation_level": "manager",
            "approver": "Line Manager",
            "total_amount": total_amount,
            "manager_approval_limit": manager_limit,
            "reason": f"Amount ₹{total_amount:,.0f} exceeds self-approval limit (₹{self_limit:,.0f}) for {grade_label}. Manager approval required.",
            "policy_reference": "Policy Section 6 – Approval Matrix",
            "requires_manual_review": False
        }
    elif total_amount <= finance_limit:
        return {
            "escalation_needed": True,
            "escalation_level": "finance",
            "approver": "Finance Team",
            "total_amount": total_amount,
            "finance_approval_limit": finance_limit,
            "reason": f"Amount ₹{total_amount:,.0f} exceeds manager approval limit (₹{manager_limit:,.0f}) for {grade_label}. Finance team approval required.",
            "policy_reference": "Policy Section 6 – Approval Matrix",
            "requires_manual_review": True
        }
    else:
        return {
            "escalation_needed": True,
            "escalation_level": "cfo",
            "approver": "CFO",
            "total_amount": total_amount,
            "cfo_approval_limit": cfo_limit,
            "reason": f"Amount ₹{total_amount:,.0f} exceeds Finance team limit (₹{finance_limit:,.0f}) for {grade_label}. CFO approval required.",
            "policy_reference": "Policy Section 6 – Approval Matrix",
            "requires_manual_review": True
        }

# ── Tool 3: get_all_grades ────────────────────────────────────────────────────
@mcp.tool()
def get_all_grades() -> dict:
    """
    Returns the full approval matrix for all employee grades.

    Returns:
        dict with list of grade records
    """
    df = _load_matrix()
    return {
        "grades": df.to_dict(orient="records"),
        "policy_reference": "Policy Section 6 – Approval Matrix"
    }

# ── Run MCP Server ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    mcp.run(transport="stdio")
