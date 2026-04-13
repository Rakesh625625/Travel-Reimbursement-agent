import re
from datetime import datetime
from langchain_core.messages import HumanMessage, SystemMessage
from agent.state import ClaimState
from agent.logger import logger

# ── Jailbreak / Prompt Injection Patterns ───────────────────────────────────
# These patterns are common indicators that a user is trying to override the system instructions.
JAILBREAK_PATTERNS = [
    r"ignore (all )?previous instructions",
    r"system prompt",
    r"you are now (a|an)",
    r"as a developer",
    r"dan mode",
    r"jailbreak",
    r"forget your rules",
    r"bypass.*policy",
    r"disregard (the )?instructions",
    r"output raw",
    r"stop being",
    r"new personality",
]

def input_guardrail_node(state: ClaimState) -> dict:
    """
    Scans incoming claim data for prompt injection attempts.
    This is the first line of defense before any LLM processing.
    """
    claim_id = state.get("claim_id", "N/A")
    logger.info(f"Node: input_guardrail | Claim: {claim_id} | Start")
    
    trace = list(state.get("audit_trace", []))
    trace.append(f"[{datetime.utcnow().isoformat()}Z] NODE: input_guardrail started")
    
    # 1. Gather text fields to scan
    text_to_scan = f"{state.get('trip_purpose', '')} {state.get('notes', '')}".lower()
    
    # 2. Pattern Matching
    violation_found = False
    violation_note = ""
    
    for pattern in JAILBREAK_PATTERNS:
        if re.search(pattern, text_to_scan):
            violation_found = True
            violation_note = f"Prompt Injection Pattern Detected: {pattern}"
            logger.warning(f"SECURITY ALERT: Input Guardrail triggered for Claim {claim_id} | Pattern: {pattern}")
            break
            
    if violation_found:
        trace.append(f"  ❌ VIOLATION: {violation_note}")
        trace.append(f"[{datetime.utcnow().isoformat()}Z] NODE: input_guardrail completed — BLOCKED")
        return {
            "safety_violation": True,
            "safety_notes": violation_note,
            "safety_check": "Blocked",
            "decision": "Rejected",
            "confidence": "High",
            "explanation": "This claim has been automatically blocked by our AI Security Layer due to detected adversarial input patterns.",
            "audit_trace": trace,
            "final_output": {
                "claim_id": state.get("claim_id"),
                "employee_id": state.get("employee_id"),
                "employee_name": state.get("employee_name"),
                "decision": "Rejected",
                "confidence": "High",
                "total_claimed": state.get("total_claimed", 0.0),
                "approved_amount": 0.0,
                "deducted_amount": 0.0,
                "rejected_amount": state.get("total_claimed", 0.0),
                "explanation": "This claim has been automatically blocked by our AI Security Layer due to detected adversarial input patterns.",
                "audit_trace": trace,
                "safety_check": "Blocked"
            }
        }
    
    trace.append("  ✅ Clear: No prompt injection patterns detected.")
    trace.append(f"[{datetime.utcnow().isoformat()}Z] NODE: input_guardrail completed — SAFE")
    
    logger.info(f"Node: input_guardrail | Claim: {claim_id} | Safe")
    return {
        "safety_violation": False,
        "safety_notes": "",
        "audit_trace": trace
    }

def output_guardrail_node(state: ClaimState) -> dict:
    """
    Evaluates the final generated explanation for hallucinations or unsafe content.
    Prevents the agent from leaking system prompts or making false policy claims.
    """
    claim_id = state.get("claim_id", "N/A")
    logger.info(f"Node: output_guardrail | Claim: {claim_id} | Start")
    
    trace = list(state.get("audit_trace", []))
    trace.append(f"[{datetime.utcnow().isoformat()}Z] NODE: output_guardrail started")
    
    explanation = state.get("explanation", "")
    
    # Check for prompt leakage or typical AI apology patterns
    safety_issue = False
    if "as an AI language model" in explanation or "I am an AI" in explanation:
        safety_issue = True
        logger.warning(f"SAFETY: Output Guardrail flagged AI-persona leakage in Claim {claim_id}")
        
    if "ignore" in explanation.lower() and "instruction" in explanation.lower():
        safety_issue = True
        logger.warning(f"SECURITY: Output Guardrail flagged potential prompt reflection in Claim {claim_id}")

    if safety_issue:
        sanitized_explanation = "The reimbursement decision has been processed, but the detailed explanation was flagged by our safety filters. Manual verification required."
        trace.append("  ⚠️ Flagged: Output sanitized due to safety filters.")
        return {
            "explanation": sanitized_explanation,
            "safety_check": "Flagged",
            "audit_trace": trace
        }

    trace.append("  ✅ Clear: Output passed safety validation.")
    trace.append(f"[{datetime.utcnow().isoformat()}Z] NODE: output_guardrail completed")
    
    return {
        "safety_check": "Passed",
        "audit_trace": trace
    }
