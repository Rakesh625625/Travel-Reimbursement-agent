"""
LangGraph Agent Graph for Travel Reimbursement Approval.

Graph Flow:
    START
      └─► policy_retrieval_node
            └─► receipt_validation_node
                  └─► approval_matrix_node
                        └─► calculation_node
                              └─► decision_node
                                    └─► END
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langgraph.graph import StateGraph, START, END
from agent.state import ClaimState
from agent.nodes import (
    policy_retrieval_node,
    receipt_validation_node,
    approval_matrix_node,
    calculation_node,
    decision_node,
)
from agent.guardrails import (
    input_guardrail_node,
    output_guardrail_node,
)


def build_graph() -> StateGraph:
    """Builds and compiles the Travel Reimbursement LangGraph."""

    builder = StateGraph(ClaimState)
    
    # ── Register nodes ──────────────────────────────────────────────────────────
    builder.add_node("input_guardrail", input_guardrail_node)
    builder.add_node("policy_retrieval", policy_retrieval_node)
    builder.add_node("receipt_validation", receipt_validation_node)
    builder.add_node("approval_matrix", approval_matrix_node)
    builder.add_node("calculation", calculation_node)
    builder.add_node("decision", decision_node)
    builder.add_node("output_guardrail", output_guardrail_node)

    # ── Wire edges ──────────────────────────────────────────────────────────────
    
    # 1. Entry Guardrail with Routing
    builder.add_edge(START, "input_guardrail")
    
    def safety_routing(state: ClaimState):
        if state.get("safety_violation", False):
            return "blocked"
        return "safe"
        
    builder.add_conditional_edges(
        "input_guardrail",
        safety_routing,
        {
            "blocked": END,
            "safe": "policy_retrieval"
        }
    )

    # 2. Main Logic Flow
    builder.add_edge("policy_retrieval", "receipt_validation")
    builder.add_edge("receipt_validation", "approval_matrix")
    builder.add_edge("approval_matrix", "calculation")
    builder.add_edge("calculation", "decision")
    
    # 3. Output Guardrail
    builder.add_edge("decision", "output_guardrail")
    builder.add_edge("output_guardrail", END)

    return builder.compile()


# ── Module-level compiled graph (import this) ───────────────────────────────────
graph = build_graph()
