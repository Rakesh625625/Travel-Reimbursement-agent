"""
MCP Server 2: Receipt Validation Server
Validates claim receipts for completeness and eligibility.

Tools exposed:
  - validate_receipts(claim_items)          -> missing docs, mismatches, validity
  - check_eligibility(expense_category)     -> eligible or ineligible with reason
  - check_receipt_policy(amount, category)  -> what receipt threshold applies
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastmcp import FastMCP
from config import RECEIPTS_DIR, RECEIPT_REQUIRED_ABOVE, RECEIPT_FORGIVENESS_LIMIT, PARTIAL_RECEIPT_REIMBURSEMENT
from agent.logger import logger

# ── Initialize MCP Server ────────────────────────────────────────────────────
mcp = FastMCP(
    name="receipt-server",
    instructions="Validates receipt completeness and expense category eligibility for reimbursement claims."
)

# ── Constants ─────────────────────────────────────────────────────────────────
INELIGIBLE_CATEGORIES = [
    "minibar", "entertainment", "gym", "spa", "alcohol",
    "fine", "laundry", "personal_phone", "luxury_upgrade",
    "family_travel", "personal_entertainment"
]

ELIGIBLE_CATEGORIES = [
    "hotel", "meal", "taxi", "flight", "local_transport",
    "conference", "visa", "travel_insurance"
]

# Mocked receipt file registry (in production, this would be a DB lookup)
RECEIPT_REGISTRY = {
    "CLM001_hotel_receipt.txt",
    "CLM001_meal_receipt.txt",
    "CLM001_taxi_receipt.txt",
    "CLM002_hotel_receipt.txt",
    "CLM002_meal_receipt.txt",
    "CLM005_flight_receipt.txt",
    "CLM005_hotel_receipt.txt",
    "CLM005_meal_receipt.txt",
    "CLM005_taxi_receipt.txt",
    "CLM004_meal_receipt.txt",
    "CLM003_hotel_receipt.txt",
    "CLM003_minibar_receipt.txt",
    "CLM003_entertainment_receipt.txt",
}

# ── Tool 1: check_eligibility ─────────────────────────────────────────────────
@mcp.tool()
def check_eligibility(expense_category: str) -> dict:
    """
    Checks whether an expense category is eligible for reimbursement.

    Args:
        expense_category: The expense type (e.g., 'hotel', 'minibar', 'taxi')

    Returns:
        dict with is_eligible, reason, policy_reference
    """
    cat = expense_category.lower().strip()

    if cat in INELIGIBLE_CATEGORIES:
        return {
            "expense_category": expense_category,
            "is_eligible": False,
            "reason": f"'{expense_category}' is explicitly listed as non-reimbursable.",
            "policy_reference": "Policy Section 3 – Ineligible Expenses",
            "action": "REJECT this line item"
        }
    elif cat in ELIGIBLE_CATEGORIES:
        return {
            "expense_category": expense_category,
            "is_eligible": True,
            "reason": f"'{expense_category}' is an approved reimbursable expense category.",
            "policy_reference": "Policy Section 2 – Eligible Categories",
            "action": "Validate amount against per-diem limits"
        }
    else:
        return {
            "expense_category": expense_category,
            "is_eligible": None,
            "reason": f"'{expense_category}' is not explicitly listed in policy.",
            "policy_reference": "FAQ Q3 – Ambiguous categories",
            "action": "ROUTE TO MANUAL REVIEW — ambiguous category"
        }

# ── Tool 2: check_receipt_policy ─────────────────────────────────────────────
@mcp.tool()
def check_receipt_policy(amount: float, expense_category: str, receipt_available: bool) -> dict:
    """
    Determines the receipt handling rule for a given amount and category.

    Args:
        amount: Expense amount in INR
        expense_category: Type of expense
        receipt_available: Whether receipt was provided

    Returns:
        dict with action, reimbursable_amount, deduction, reason, policy_reference
    """
    # Categories that always require receipt regardless of amount
    always_requires_receipt = ["hotel", "flight"]

    cat = expense_category.lower()

    if receipt_available:
        return {
            "receipt_available": True,
            "action": "PROCEED",
            "reimbursable_percentage": 1.0,
            "reason": "Receipt provided — proceed to amount validation.",
            "policy_reference": "Policy Section 5 – Receipt Requirements"
        }

    # No receipt cases
    if amount <= RECEIPT_FORGIVENESS_LIMIT:
        return {
            "receipt_available": False,
            "amount": amount,
            "action": "APPROVE_WITHOUT_RECEIPT",
            "reimbursable_percentage": 1.0,
            "reimbursable_amount": amount,
            "deduction": 0,
            "reason": f"Amount ≤ ₹{RECEIPT_FORGIVENESS_LIMIT} — approved without receipt per policy.",
            "policy_reference": "Policy Section 5 – Receipt not required up to ₹200"
        }
    elif cat in always_requires_receipt:
        return {
            "receipt_available": False,
            "amount": amount,
            "action": "REJECT",
            "reimbursable_percentage": 0.0,
            "reimbursable_amount": 0,
            "deduction": amount,
            "reason": f"'{expense_category}' always requires a receipt. No exceptions for amounts > ₹{RECEIPT_FORGIVENESS_LIMIT}.",
            "policy_reference": "Policy Section 5 – Hotel/Flight always require receipt"
        }
    elif amount <= 500:
        partial = round(amount * PARTIAL_RECEIPT_REIMBURSEMENT, 2)
        return {
            "receipt_available": False,
            "amount": amount,
            "action": "PARTIAL_APPROVE",
            "reimbursable_percentage": PARTIAL_RECEIPT_REIMBURSEMENT,
            "reimbursable_amount": partial,
            "deduction": round(amount - partial, 2),
            "reason": f"Amount ₹201–₹500 without receipt — reimbursed at {int(PARTIAL_RECEIPT_REIMBURSEMENT*100)}% per policy.",
            "policy_reference": "Policy Section 5 – Partial reimbursement for missing receipt ₹201–₹500"
        }
    else:
        return {
            "receipt_available": False,
            "amount": amount,
            "action": "REJECT",
            "reimbursable_percentage": 0.0,
            "reimbursable_amount": 0,
            "deduction": amount,
            "reason": f"Amount > ₹500 without receipt — rejected per policy. Emergency override requires manager email.",
            "policy_reference": "Policy Section 5 – Expenses > ₹500 without receipt rejected"
        }

# ── Tool 3: validate_receipts ─────────────────────────────────────────────────
@mcp.tool()
def validate_receipts(claim_items: list) -> dict:
    """
    Validates all receipt items in a claim.

    Args:
        claim_items: List of expense items, each with:
            - item_id, type, amount, receipt_available, receipt_ref (optional)

    Returns:
        dict with:
            - valid_items: items with valid receipts
            - missing_receipt_items: items missing receipts
            - ineligible_items: items with ineligible category
            - ambiguous_items: items with unclear category
            - requires_manual_review: bool
            - manual_review_reasons: list of reasons
            - summary
    """
    valid_items = []
    missing_receipt_items = []
    ineligible_items = []
    ambiguous_items = []
    manual_review_reasons = []

    for item in claim_items:
        item_id = item.get("item_id", "unknown")
        category = item.get("type", "unknown")
        amount = float(item.get("amount", 0))
        receipt_available = item.get("receipt_available", False)
        receipt_ref = item.get("receipt_ref", None)

        # 1. Check eligibility
        eligibility = check_eligibility(category)

        if eligibility["is_eligible"] is False:
            ineligible_items.append({
                "item_id": item_id,
                "type": category,
                "amount": amount,
                "reason": eligibility["reason"],
                "policy_reference": eligibility["policy_reference"]
            })
            continue

        if eligibility["is_eligible"] is None:
            ambiguous_items.append({
                "item_id": item_id,
                "type": category,
                "amount": amount,
                "reason": eligibility["reason"]
            })
            manual_review_reasons.append(f"Ambiguous category '{category}' on item {item_id}")
            continue

        # 2. Check receipt
        receipt_check = check_receipt_policy(amount, category, receipt_available)

        if receipt_check["action"] in ("REJECT", "PARTIAL_APPROVE"):
            missing_receipt_items.append({
                "item_id": item_id,
                "type": category,
                "amount": amount,
                "receipt_available": receipt_available,
                "action": receipt_check["action"],
                "reimbursable_amount": receipt_check["reimbursable_amount"],
                "deduction": receipt_check["deduction"],
                "reason": receipt_check["reason"],
                "policy_reference": receipt_check["policy_reference"]
            })
            # Large missing receipts warrant manual review
            if amount > 5000 and not receipt_available:
                manual_review_reasons.append(
                    f"High-value item ({category}, ₹{amount}) missing receipt — item {item_id}"
                )
        else:
            valid_items.append({
                "item_id": item_id,
                "type": category,
                "amount": amount,
                "receipt_available": receipt_available
            })

    # Determine if manual review is needed
    missing_critical = any(
        i["type"] in ("flight", "hotel") for i in missing_receipt_items
        if i.get("action") == "REJECT"
    )
    if missing_critical:
        manual_review_reasons.append("Critical receipts missing (flight/hotel) — requires human verification")

    requires_manual_review = len(manual_review_reasons) > 0

    logger.info(f"MCP: validate_receipts | processing {len(claim_items)} items")
    return {
        "valid_items": valid_items,
        "missing_receipt_items": missing_receipt_items,
        "ineligible_items": ineligible_items,
        "ambiguous_items": ambiguous_items,
        "requires_manual_review": requires_manual_review,
        "manual_review_reasons": manual_review_reasons,
        "summary": {
            "total_items": len(claim_items),
            "valid": len(valid_items),
            "missing_receipt": len(missing_receipt_items),
            "ineligible": len(ineligible_items),
            "ambiguous": len(ambiguous_items)
        }
    }

# ── Run MCP Server ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    mcp.run(transport="stdio")
