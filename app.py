"""
Streamlit Frontend for Travel Reimbursement Approval Agent.
Provides a simple UI to submit claims and view the AI's decision and audit trace.
"""

import sys
import os
import requests
import pandas as pd
import streamlit as st

# Ensure we can import config
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from config import API_PORT, API_HOST

API_URL = f"http://{API_HOST if API_HOST != '0.0.0.0' else 'localhost'}:{API_PORT}"

st.set_page_config(
    page_title="Travel Claim Agent",
    page_icon="✈️",
    layout="wide"
)

# ── Custom CSS ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .decision-Approve { color: #2e7d32; font-weight: bold; font-size: 1.2em; }
    .decision-Partially { color: #f57c00; font-weight: bold; font-size: 1.2em; }
    .decision-Reject { color: #c62828; font-weight: bold; font-size: 1.2em; }
    .decision-Manual { color: #1565c0; font-weight: bold; font-size: 1.2em; }
    .metric-card { background-color: #f8f9fa; padding: 15px; border-radius: 8px; border: 1px solid #e0e0e0; }
</style>
""", unsafe_allow_html=True)


# ── API Configuration ────────────────────────────────────────────────────────
API_BASE_URL = os.getenv("API_URL", "http://localhost:8000")

# ── API Calls ──────────────────────────────────────────────────────────────
def fetch_sample_claims():
    try:
        response = requests.get(f"{API_URL}/claims/sample")
        if response.status_code == 200:
            return response.json().get("samples", [])
    except requests.exceptions.ConnectionError:
        st.error(f"Cannot connect to backend API at {API_URL}. Is it running?")
    return []

def run_sample_claim(claim_id):
    with st.spinner(f"Agent processing claim {claim_id}..."):
        try:
            response = requests.post(f"{API_URL}/claims/sample/{claim_id}")
            if response.status_code == 200:
                return response.json()
            else:
                st.error(f"Error: {response.text}")
        except Exception as e:
            st.error(f"Request failed: {e}")
    return None


# ── UI Layout ──────────────────────────────────────────────────────────────
st.title("✈️ Travel Reimbursement Approval Agent")
st.markdown("*AI-powered evaluation of travel expenses against company policy using LangGraph and MCP.*")

# Main Navigation
nav_selection = st.sidebar.radio("Navigation Menu", ["🧳 Process Claims", "💁 Policy Chatbot"])
st.sidebar.markdown("---")

if nav_selection == "🧳 Process Claims":
    # Sidebar for controls
    with st.sidebar:
        st.header("Upload Claim")
        
        upload_file = st.file_uploader("Upload custom claim (JSON)", type=["json"])
        process_btn = st.button("🚀 Process via Agent", type="primary", use_container_width=True)

    # Main content area
    result = None
    if upload_file is not None and process_btn:
        import json
        with st.spinner("Agent processing custom claim..."):
            try:
                custom_json = json.load(upload_file)
                response = requests.post(f"{API_URL}/claims/process", json=custom_json)
                if response.status_code == 200:
                    result = response.json()
                else:
                    st.error(f"Error: {response.text}")
            except Exception as e:
                st.error(f"Failed to process uploaded file: {e}")
                
    if result:
        # Top banner with final decision
        decision = result['decision']
        color_class = "decision-Approve"
        if "Partially" in decision: color_class = "decision-Partially"
        elif "Reject" in decision: color_class = "decision-Reject"
        elif "Manual" in decision: color_class = "decision-Manual"
        
        st.markdown(f"### Result: <span class='{color_class}'>{decision}</span>", unsafe_allow_html=True)
        st.markdown(f"**Explanation:** {result['explanation']}")

        if result.get('requires_manual_review'):
            st.warning("⚠️ This claim has been flagged for Manual Review.")
            if result.get('escalation_level'):
                st.info(f"⬆️ Escalation Required: **{result['escalation_level'].upper()}** ({result.get('escalation_reason')})")

        # Amount Summary Metrics
        st.markdown("---")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Claimed", f"₹ {result['total_claimed']:,.2f}")
        col2.metric("Approved Amount", f"₹ {result['approved_amount']:,.2f}", 
                   delta=f"₹ {result['approved_amount'] - result['total_claimed']:,.2f}" if result['approved_amount'] < result['total_claimed'] else None)
        col3.metric("Amount Deducted", f"₹ {result['deducted_amount']:,.2f}")
        col4.metric("Amount Rejected", f"₹ {result['rejected_amount']:,.2f}")

        st.markdown("---")
        
        # Tabs for detailed breakdown
        tab1, tab2, tab3, tab4 = st.tabs(["📋 Line Items Summary", "📑 Policy & Violations", "🔍 Missing Documents", "⚙️ Agent Audit Trace"])
        
        with tab1:
            st.subheader("Itemized Breakdown")
            
            # Combine items for display
            all_items = []
            for item in result.get('approved_items', []):
                item['Status'] = '✅ Approved'
                all_items.append(item)
            for item in result.get('deducted_items', []):
                item['Status'] = '⚠️ Deducted'
                item['amount'] = item.get('claimed_amount', 0)
                all_items.append(item)
            for item in result.get('rejected_items', []):
                item['Status'] = '❌ Rejected'
                all_items.append(item)
                
            if all_items:
                df = pd.DataFrame(all_items)
                
                # Ensure columns exist to prevent KeyError
                if 'reason' not in df.columns:
                    df['reason'] = '-'
                if 'approved_amount' not in df.columns:
                    df['approved_amount'] = 0
                    
                display_df = df[['item_id', 'type', 'amount', 'Status', 'approved_amount', 'reason']].copy()
                display_df['reason'] = display_df['reason'].fillna('-')
                display_df['approved_amount'] = display_df['approved_amount'].fillna(0.0)
                display_df['amount'] = display_df['amount'].fillna(0.0)
                st.dataframe(display_df, use_container_width=True)
        
        with tab2:
            st.subheader("Policy Citations Applied")
            if result.get('policy_references'):
                for ref in result['policy_references']:
                    st.markdown(f"- 📖 `{ref}`")
            else:
                st.write("No specific policy clauses cited.")
                
            st.subheader("Violations / Deductions")
            violations = result.get('deducted_items', []) + result.get('rejected_items', [])
            if violations:
                for v in violations:
                    st.error(f"**{v['type'].title()}** (Item: {v['item_id']}): {v['reason']}")
            else:
                st.success("No violations found.")

        with tab3:
            st.subheader("Missing Documentation")
            if result.get('missing_documents'):
                for doc in result['missing_documents']:
                    st.warning(f"📄 {doc}")
            else:
                st.success("All required documentation is present.")

        with tab4:
            st.subheader("Agent Execution Trace")
            st.markdown(f"*Processing Time: `{result['processing_time_seconds']}s` | Confidence: `{result['confidence']}`*")
            
            with st.expander("View LangGraph steps", expanded=True):
                for step in result.get('audit_trace', []):
                    if "NODE" in step:
                        st.markdown(f"**{step}**")
                    else:
                        st.text(step)
    else:
        if not process_btn:
            st.info("👈 Upload a claim from the sidebar and click 'Process via Agent'")

elif nav_selection == "💁 Policy Chatbot":
    st.header("Policy & FAQ Chatbot")
    st.markdown("Ask any question about corporate travel policies, per-diems, and allowed exceptions.")
    
    # Initialize chat history
    if "messages" not in st.session_state:
        st.session_state.messages = []
        st.session_state.messages.append({"role": "assistant", "content": "Hello! I am your AI Travel Policy Assistant. How can I help you today?"})

    # Display chat messages from history on app rerun
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Accept user input
    if prompt := st.chat_input("Ask a policy question..."):
        # Display user message in chat message container
        with st.chat_message("user"):
            st.markdown(prompt)
        
        # Format history for API
        history = st.session_state.messages.copy()
        
        # Add user message to chat history
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        # Get AI response
        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            with st.spinner("Searching policy..."):
                try:
                    payload = {"query": prompt, "history": history}
                    response = requests.post(f"{API_URL}/faq/chat", json=payload)
                    if response.status_code == 200:
                        full_response = response.json().get("answer", "I could not generate an answer.")
                        message_placeholder.markdown(full_response)
                        st.session_state.messages.append({"role": "assistant", "content": full_response})
                    else:
                        st.error(f"Error from Chat Engine: {response.text}")
                except Exception as e:
                    st.error(f"Failed to connect to backend: {e}")
