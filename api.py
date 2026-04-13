"""
FastAPI Backend for Travel Reimbursement Approval Agent.

Endpoints:
  POST /claims/process          — Submit a new claim for processing
  GET  /claims/sample           — Get list of built-in sample claims
  POST /claims/sample/{claim_id} — Run a sample claim by ID
  GET  /health                  — Health check
  GET  /docs                    — Auto-generated Swagger UI (by FastAPI)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json
import time
from typing import List, Optional
from datetime import datetime

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from agent.graph import graph
from agent.state import ClaimState
from agent.rag_service import rag_service
from agent.logger import logger
from config import SAMPLE_CLAIMS_FILE


# ── FastAPI App ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="Travel Reimbursement Approval Agent",
    description="""
## 🧳 Travel Reimbursement Approval Agent

An AI-powered system that automatically evaluates employee travel claims against
company policy using **LangGraph** orchestration and **MCP** tool integration.

### Key Features
- **Policy-aware**: Checks per-diem limits, eligible categories, receipt thresholds
- **Receipt validation**: Flags missing receipts and applies partial reimbursement rules
- **Grade-based approval**: Escalates to manager/finance/CFO based on employee grade
- **LLM reasoning**: Generates human-readable explanations with full audit trail
- **Structured output**: Returns validated `DecisionOutput` with Pydantic schema

### Decision Types
| Decision | Meaning |
|---|---|
| `Approve` | Fully approved within limits |
| `Partially Approve` | Some items capped or deducted |
| `Reject` | Ineligible categories or missing critical docs |
| `Manual Review` | Ambiguous items or escalation required |
""",
    version="1.0.0",
    contact={"name": " Assessment – Rakesh"}
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response Schemas ────────────────────────────────────────────────
class ClaimItem(BaseModel):
    item_id: str
    type: str
    description: str
    amount: float
    quantity: int = 1
    unit: str = "item"
    receipt_available: bool = True
    receipt_ref: Optional[str] = None


class ClaimRequest(BaseModel):
    claim_id: str = Field(..., example="CLM-2024-001")
    employee_id: str = Field(..., example="EMP-042")
    employee_name: str = Field(..., example="Priya Sharma")
    employee_grade: str = Field(..., example="L3", description="L1–L7")
    department: str = Field(..., example="Engineering")
    trip_city: str = Field(..., example="Mumbai")
    trip_country: str = Field(..., example="India")
    trip_type: str = Field(..., example="domestic", description="domestic or international")
    trip_purpose: str = Field(..., example="Client meeting")
    travel_start_date: str = Field(..., example="2024-01-15")
    travel_end_date: str = Field(..., example="2024-01-17")
    submission_date: str = Field(default_factory=lambda: datetime.utcnow().strftime("%Y-%m-%d"))
    items: List[ClaimItem]
    total_claimed: float
    manager_id: str = Field(..., example="EMP-010")
    notes: str = ""


class ChatRequest(BaseModel):
    query: str = Field(..., example="What is the taxi limit in Mumbai?")
    history: List[dict] = Field(default_factory=list, description="List of previous messages")

class ProcessResponse(BaseModel):
    claim_id: str
    decision: str
    confidence: str
    total_claimed: float
    approved_amount: float
    deducted_amount: float
    rejected_amount: float
    explanation: str
    requires_manual_review: bool
    escalation_level: Optional[str] = None
    escalation_reason: Optional[str] = None
    approved_items: list = []
    deducted_items: list = []
    rejected_items: list = []
    missing_documents: list = []
    policy_references: list = []
    audit_trace: list = []
    safety_check: str = "Passed"
    processed_at: str
    processing_time_seconds: float


# ── Helper: load sample claims ────────────────────────────────────────────────
def _load_sample_claims() -> list:
    with open(SAMPLE_CLAIMS_FILE, "r") as f:
        return json.load(f)


def _build_state_from_request(req: ClaimRequest) -> dict:
    """Converts API request to ClaimState-compatible dict."""
    return {
        "claim_id": req.claim_id,
        "employee_id": req.employee_id,
        "employee_name": req.employee_name,
        "employee_grade": req.employee_grade,
        "department": req.department,
        "trip_city": req.trip_city,
        "trip_country": req.trip_country,
        "trip_type": req.trip_type,
        "trip_purpose": req.trip_purpose,
        "travel_start_date": req.travel_start_date,
        "travel_end_date": req.travel_end_date,
        "submission_date": req.submission_date,
        "claim_items": [item.model_dump() for item in req.items],
        "total_claimed": req.total_claimed,
        "manager_id": req.manager_id,
        "notes": req.notes,
        # Initialize all downstream fields with defaults
        "per_diem_limits": {},
        "policy_rules": {},
        "full_policy_text": "",
        "valid_items": [],
        "missing_receipt_items": [],
        "ineligible_items": [],
        "ambiguous_items": [],
        "missing_documents": [],
        "approval_thresholds": {},
        "escalation_result": {},
        "approved_items": [],
        "deducted_items": [],
        "rejected_items": [],
        "approved_amount": 0.0,
        "deducted_amount": 0.0,
        "rejected_amount": 0.0,
        "requires_manual_review": False,
        "manual_review_reasons": [],
        "flags": [],
        "messages": [],
        "decision": "",
        "confidence": "",
        "explanation": "",
        "policy_references": [],
        "audit_trace": [],
        "safety_violation": False,
        "safety_notes": "",
        "safety_check": "Passed",
        "final_output": {},
    }


def _build_state_from_sample(raw: dict) -> dict:
    """Converts raw sample JSON to ClaimState-compatible dict."""
    return {
        "claim_id": raw["claim_id"],
        "employee_id": raw["employee_id"],
        "employee_name": raw["employee_name"],
        "employee_grade": raw["employee_grade"],
        "department": raw["department"],
        "trip_city": raw["trip_city"],
        "trip_country": raw["trip_country"],
        "trip_type": raw["trip_type"],
        "trip_purpose": raw["trip_purpose"],
        "travel_start_date": raw["travel_start_date"],
        "travel_end_date": raw["travel_end_date"],
        "submission_date": raw["submission_date"],
        "claim_items": raw["items"],
        "total_claimed": raw["total_claimed"],
        "manager_id": raw["manager_id"],
        "notes": raw.get("notes", ""),
        "per_diem_limits": {},
        "policy_rules": {},
        "full_policy_text": "",
        "valid_items": [],
        "missing_receipt_items": [],
        "ineligible_items": [],
        "ambiguous_items": [],
        "missing_documents": [],
        "approval_thresholds": {},
        "escalation_result": {},
        "approved_items": [],
        "deducted_items": [],
        "rejected_items": [],
        "approved_amount": 0.0,
        "deducted_amount": 0.0,
        "rejected_amount": 0.0,
        "requires_manual_review": False,
        "manual_review_reasons": [],
        "flags": [],
        "messages": [],
        "decision": "",
        "confidence": "",
        "explanation": "",
        "policy_references": [],
        "audit_trace": [],
        "safety_violation": False,
        "safety_notes": "",
        "safety_check": "Passed",
        "final_output": {},
    }


def _run_graph(initial_state: dict) -> ProcessResponse:
    """Runs the LangGraph and returns a ProcessResponse."""
    claim_id = initial_state.get("claim_id", "unknown")
    logger.info(f"Starting LangGraph execution for Claim: {claim_id}")
    
    start = time.time()
    try:
        final_state = graph.invoke(initial_state)
    except Exception as e:
        logger.error(f"LangGraph execution failed for Claim {claim_id}: {str(e)}")
        raise e
        
    elapsed = round(time.time() - start, 2)
    logger.info(f"LangGraph execution completed for Claim {claim_id} in {elapsed}s")

    fo = final_state.get("final_output", {})
    
    # Prioritize safety fields from the top-level state if final_output is incomplete
    safety_c = final_state.get("safety_check", "Passed")
    if final_state.get("safety_violation"):
        safety_c = "Blocked"

    return ProcessResponse(
        claim_id=fo.get("claim_id", initial_state["claim_id"]),
        decision=fo.get("decision", "Rejected" if final_state.get("safety_violation") else "Manual Review"),
        confidence=fo.get("confidence", "High" if final_state.get("safety_violation") else "Low"),
        total_claimed=fo.get("total_claimed", initial_state["total_claimed"]),
        approved_amount=fo.get("approved_amount", 0.0),
        deducted_amount=fo.get("deducted_amount", 0.0),
        rejected_amount=fo.get("rejected_amount", initial_state["total_claimed"] if final_state.get("safety_violation") else 0.0),
        explanation=fo.get("explanation", final_state.get("explanation", "")),
        requires_manual_review=fo.get("requires_manual_review", False),
        escalation_level=fo.get("escalation_level"),
        escalation_reason=fo.get("escalation_reason"),
        approved_items=fo.get("approved_items", []),
        deducted_items=fo.get("deducted_items", []),
        rejected_items=fo.get("rejected_items", []),
        missing_documents=fo.get("missing_documents", []),
        policy_references=fo.get("policy_references", []),
        audit_trace=fo.get("audit_trace", final_state.get("audit_trace", [])),
        safety_check=safety_c,
        processed_at=fo.get("processed_at", datetime.utcnow().isoformat() + "Z"),
        processing_time_seconds=elapsed,
    )


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
def health():
    """Health check endpoint."""
    logger.info("Health check requested")
    return {"status": "ok", "service": "travel-reimbursement-agent", "timestamp": datetime.utcnow().isoformat() + "Z"}


@app.get("/claims/sample", tags=["Claims"])
def list_sample_claims():
    """
    Returns the list of built-in sample claims with their scenario labels.
    Use claim_id values with POST /claims/sample/{claim_id} to run them.
    """
    claims = _load_sample_claims()
    return {
        "total": len(claims),
        "samples": [
            {
                "claim_id": c["claim_id"],
                "employee_name": c["employee_name"],
                "employee_grade": c["employee_grade"],
                "trip_city": c["trip_city"],
                "trip_type": c["trip_type"],
                "total_claimed": c["total_claimed"],
                "scenario_label": c.get("scenario_label", ""),
            }
            for c in claims
        ]
    }


@app.post("/claims/sample/{claim_id}", response_model=ProcessResponse, tags=["Claims"])
def run_sample_claim(claim_id: str):
    """
    Runs a pre-built sample claim through the full agent pipeline.

    Available claim IDs: CLM-2024-001 through CLM-2024-005
    """
    claims = _load_sample_claims()
    raw = next((c for c in claims if c["claim_id"] == claim_id), None)
    if not raw:
        raise HTTPException(status_code=404, detail=f"Sample claim '{claim_id}' not found.")

    initial_state = _build_state_from_sample(raw)
    try:
        return _run_graph(initial_state)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent processing error: {str(e)}")


@app.post("/claims/process", response_model=ProcessResponse, tags=["Claims"])
def process_claim(req: ClaimRequest):
    """
    Submits a new travel reimbursement claim for AI-powered evaluation.

    The agent will:
    1. Retrieve applicable policy rules and per-diem limits
    2. Validate receipts and eligibility of each expense item
    3. Apply grade-based approval thresholds and escalation logic
    4. Calculate approved/deducted/rejected amounts
    5. Generate a structured decision with an LLM explanation
    """
    initial_state = _build_state_from_request(req)
    try:
        return _run_graph(initial_state)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent processing error: {str(e)}")

@app.post("/faq/chat", tags=["FAQ"])
def chat_with_policy(req: ChatRequest):
    """
    RAG endpoint to converse with the Travel Policy and FAQ documents.
    """
    logger.info(f"FAQ Chat Request: {req.query}")
    try:
        answer = rag_service.answer_query(req.query, req.history)
        return {"answer": answer}
    except Exception as e:
        logger.error(f"RAG Chat Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"RAG engine error: {str(e)}")

