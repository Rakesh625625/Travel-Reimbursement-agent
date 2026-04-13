"""
MCP Server 1: Policy Server
Provides tools for retrieving travel policy rules and per-diem limits.

Tools exposed:
  - get_policy_rules(expense_type, city, trip_type) -> policy limits + eligibility
  - get_per_diem_limits(city, trip_type)            -> daily/per-night limits
  - get_ineligible_categories()                     -> list of non-reimbursable types
  - get_full_policy()                               -> full policy text (for LLM context)
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from fastmcp import FastMCP
from config import POLICY_FILE, INTERNATIONAL_POLICY_FILE, PER_DIEM_FILE, FAQ_FILE
from agent.logger import logger

# ── Initialize MCP Server ────────────────────────────────────────────────────
mcp = FastMCP(
    name="policy-server",
    instructions="Provides travel reimbursement policy rules, per-diem limits, and eligibility information."
)

# ── Ineligible categories (hard-coded from policy) ───────────────────────────
INELIGIBLE_CATEGORIES = [
    "minibar", "entertainment", "gym", "spa", "alcohol",
    "fine", "laundry", "personal_phone", "luxury_upgrade",
    "family_travel", "personal_entertainment"
]

# ── Load per-diem limits ──────────────────────────────────────────────────────
def _load_per_diem() -> pd.DataFrame:
    return pd.read_csv(PER_DIEM_FILE)

def _load_policy(trip_type: str = "domestic") -> str:
    if trip_type == "international":
        with open(INTERNATIONAL_POLICY_FILE, "r") as f:
            intl = f.read()
        with open(POLICY_FILE, "r") as f:
            base = f.read()
        return base + "\n\n---\n\n" + intl
    with open(POLICY_FILE, "r") as f:
        return f.read()

# ── Tool 1: get_per_diem_limits ───────────────────────────────────────────────
@mcp.tool()
def get_per_diem_limits(city: str, trip_type: str = "domestic") -> dict:
    """
    Returns per-diem expense limits for a given city and trip type.
    
    Args:
        city: Name of the city (e.g., 'Mumbai', 'New York')
        trip_type: 'domestic' or 'international'
    
    Returns:
        dict with hotel_per_night, meal_per_day, taxi_per_day, flight_max_one_way,
        local_transport_per_day. Returns nearest city limits if exact city not found.
    """
    df = _load_per_diem()

    # Exact match first
    row = df[(df["city"].str.lower() == city.lower()) & (df["trip_type"] == trip_type)]

    if row.empty:
        # Fallback: try trip_type match only (use first available city of that type)
        fallback = df[df["trip_type"] == trip_type].iloc[0] if not df[df["trip_type"] == trip_type].empty else None
        if fallback is None:
            return {
                "found": False,
                "city": city,
                "message": f"City '{city}' not found in policy. Using default limits.",
                "hotel_per_night": 3000,
                "meal_per_day": 350,
                "taxi_per_day": 250,
                "flight_max_one_way": 8000,
                "local_transport_per_day": 100,
                "city_not_in_policy": True
            }
        return {
            "found": False,
            "city": city,
            "fallback_city": fallback["city"],
            "message": f"City '{city}' not found. Using '{fallback['city']}' limits as fallback.",
            "hotel_per_night": float(fallback["hotel_per_night"]),
            "meal_per_day": float(fallback["meal_per_day"]),
            "taxi_per_day": float(fallback["taxi_per_day"]),
            "flight_max_one_way": float(fallback["flight_max_one_way"]),
            "local_transport_per_day": float(fallback["local_transport_per_day"]),
            "city_not_in_policy": True
        }

    r = row.iloc[0]
    logger.info(f"MCP: get_per_diem_limits | city={city} | found=True")
    return {
        "found": True,
        "city": r["city"],
        "country": r["country"],
        "trip_type": r["trip_type"],
        "hotel_per_night": float(r["hotel_per_night"]),
        "meal_per_day": float(r["meal_per_day"]),
        "taxi_per_day": float(r["taxi_per_day"]),
        "flight_max_one_way": float(r["flight_max_one_way"]),
        "local_transport_per_day": float(r["local_transport_per_day"]),
        "notes": str(r.get("notes", "")),
        "city_not_in_policy": False
    }

# ── Tool 2: get_policy_rules ─────────────────────────────────────────────────
@mcp.tool()
def get_policy_rules(expense_type: str, city: str, trip_type: str = "domestic") -> dict:
    """
    Returns specific policy rules for a given expense type and city.

    Args:
        expense_type: Expense category (e.g., 'hotel', 'meal', 'taxi', 'flight')
        city: City name
        trip_type: 'domestic' or 'international'

    Returns:
        dict with is_eligible, limit, receipt_required, special_rules, policy_reference
    """
    limits = get_per_diem_limits(city, trip_type)

    # Category-specific rules
    rules = {
        "hotel": {
            "is_eligible": True,
            "limit": limits["hotel_per_night"],
            "unit": "per night",
            "receipt_required": True,
            "receipt_threshold": 0,
            "special_rules": [
                "Max 4-star for domestic travel",
                "Max 5-star for international (Director approval required)",
                "Itemized bill required showing room rate separate from F&B"
            ],
            "policy_reference": "Policy Section 7 – Hotel Rules"
        },
        "meal": {
            "is_eligible": True,
            "limit": limits["meal_per_day"],
            "unit": "per day",
            "receipt_required": True,
            "receipt_threshold": 200,
            "special_rules": [
                "Combined meals (breakfast + lunch + dinner) within daily limit",
                "Client entertainment: up to 2x per-diem with guest list",
                "First/last day of travel: 75% of per-diem"
            ],
            "policy_reference": "Policy Section 7 – Meal Rules"
        },
        "taxi": {
            "is_eligible": True,
            "limit": limits["taxi_per_day"],
            "unit": "per day",
            "receipt_required": True,
            "receipt_threshold": 300,
            "special_rules": [
                "Standard taxi/cab only — no luxury vehicles",
                "Airport transfers and client visits covered",
                "Receipt required for amounts above ₹300"
            ],
            "policy_reference": "Policy Section 2 – Eligible Categories"
        },
        "flight": {
            "is_eligible": True,
            "limit": limits["flight_max_one_way"],
            "unit": "per one-way trip",
            "receipt_required": True,
            "receipt_threshold": 0,
            "special_rules": [
                "Economy class mandatory",
                "Business class allowed for flights > 6 hours",
                "E-ticket and boarding pass required",
                "48-hour advance booking required"
            ],
            "policy_reference": "Policy Section 7 – Flight Rules"
        },
        "local_transport": {
            "is_eligible": True,
            "limit": limits["local_transport_per_day"],
            "unit": "per day",
            "receipt_required": False,
            "receipt_threshold": 200,
            "special_rules": ["Metro, bus, auto-rickshaw covered"],
            "policy_reference": "Policy Section 2 – Eligible Categories"
        },
        "conference": {
            "is_eligible": True,
            "limit": None,
            "unit": "actual cost",
            "receipt_required": True,
            "receipt_threshold": 0,
            "special_rules": ["Prior manager approval required"],
            "policy_reference": "Policy Section 2 – Eligible Categories"
        },
        "visa": {
            "is_eligible": True,
            "limit": None,
            "unit": "actual cost",
            "receipt_required": True,
            "receipt_threshold": 0,
            "special_rules": ["Actual cost reimbursed with receipt"],
            "policy_reference": "Policy Section 2 – Eligible Categories"
        },
        "travel_insurance": {
            "is_eligible": True,
            "limit": None,
            "unit": "actual cost",
            "receipt_required": True,
            "receipt_threshold": 0,
            "special_rules": ["Company-approved plans only"],
            "policy_reference": "Policy Section 2 – Eligible Categories"
        }
    }

    # Ineligible categories
    if expense_type.lower() in INELIGIBLE_CATEGORIES:
        return {
            "is_eligible": False,
            "expense_type": expense_type,
            "limit": 0,
            "reason": f"'{expense_type}' is explicitly listed as non-reimbursable under company policy.",
            "policy_reference": "Policy Section 3 – Ineligible Expenses"
        }

    if expense_type.lower() in rules:
        result = rules[expense_type.lower()].copy()
        result["expense_type"] = expense_type
        return result

    # Unknown category fallback
    return {
        "is_eligible": None,
        "expense_type": expense_type,
        "limit": None,
        "reason": f"Category '{expense_type}' is not explicitly listed in policy.",
        "ambiguous": True,
        "policy_reference": "FAQ Q3 – Ambiguous categories route to Manual Review"
    }

# ── Tool 3: get_ineligible_categories ────────────────────────────────────────
@mcp.tool()
def get_ineligible_categories() -> dict:
    """
    Returns the list of all non-reimbursable expense categories per company policy.
    
    Returns:
        dict with list of ineligible categories and policy reference
    """
    return {
        "ineligible_categories": INELIGIBLE_CATEGORIES,
        "policy_reference": "Policy Section 3 – Ineligible Expenses",
        "note": "These categories are rejected regardless of receipt availability."
    }

# ── Tool 4: get_full_policy ───────────────────────────────────────────────────
@mcp.tool()
def get_full_policy(trip_type: str = "domestic") -> dict:
    """
    Returns the full policy text for use as LLM context.
    
    Args:
        trip_type: 'domestic' or 'international'
    
    Returns:
        dict with policy_text and faq_text
    """
    policy_text = _load_policy(trip_type)
    faq_text = ""
    if os.path.exists(FAQ_FILE):
        with open(FAQ_FILE, "r") as f:
            faq_text = f.read()
    return {
        "policy_text": policy_text,
        "faq_text": faq_text,
        "trip_type": trip_type
    }

# ── Run MCP Server ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    mcp.run(transport="stdio")
