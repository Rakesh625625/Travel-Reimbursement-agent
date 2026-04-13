"""
Configuration settings for Travel Reimbursement Approval Agent.
Copy this file to .env and fill in your API keys.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ─── LLM Configuration ────────────────────────────────────────────────────────
# Supported providers: "openai", "google", "anthropic"
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# ─── MCP Server Ports ─────────────────────────────────────────────────────────
POLICY_SERVER_PORT = int(os.getenv("POLICY_SERVER_PORT", "8001"))
RECEIPT_SERVER_PORT = int(os.getenv("RECEIPT_SERVER_PORT", "8002"))
APPROVAL_SERVER_PORT = int(os.getenv("APPROVAL_SERVER_PORT", "8003"))

# ─── FastAPI Settings ──────────────────────────────────────────────────────────
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))

# ─── Data Paths ───────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

POLICY_FILE = os.path.join(DATA_DIR, "policy.md")
INTERNATIONAL_POLICY_FILE = os.path.join(DATA_DIR, "international_policy.md")
PER_DIEM_FILE = os.path.join(DATA_DIR, "per_diem_limits.csv")
APPROVAL_MATRIX_FILE = os.path.join(DATA_DIR, "approval_matrix.csv")
SAMPLE_CLAIMS_FILE = os.path.join(DATA_DIR, "sample_claims.json")
RECEIPTS_DIR = os.path.join(DATA_DIR, "receipts")
FAQ_FILE = os.path.join(DATA_DIR, "faq.md")

# ─── Agent Settings ───────────────────────────────────────────────────────────
# Minimum receipt amount requiring documentation
RECEIPT_REQUIRED_ABOVE = float(os.getenv("RECEIPT_REQUIRED_ABOVE", "200"))

# % of unreceipted amount reimbursed if below threshold
PARTIAL_RECEIPT_REIMBURSEMENT = float(os.getenv("PARTIAL_RECEIPT_REIMBURSEMENT", "0.5"))

# Amount below which missing receipt is forgiven
RECEIPT_FORGIVENESS_LIMIT = float(os.getenv("RECEIPT_FORGIVENESS_LIMIT", "200"))

# LangSmith tracing (optional)
LANGCHAIN_TRACING_V2 = os.getenv("LANGCHAIN_TRACING_V2", "false")
LANGCHAIN_API_KEY = os.getenv("LANGCHAIN_API_KEY", "")
LANGCHAIN_PROJECT = os.getenv("LANGCHAIN_PROJECT", "travel-reimbursement-agent")
