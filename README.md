# ✈️ Travel Reimbursement Approval Agent

An AI-powered system that automatically evaluates employee travel claims against company policy using **LangGraph** orchestration, **MCP** (Model Context Protocol) tool integration, and Google's **Gemini**. 

This repository was created as a robust, production-grade Prototype submission for the HCL Tech AI Solution Associate Assignment.

---

## 🎯 Enterprise-Grade Features Added
- **Deterministic LangGraph Workflow**: Replaces unpredictable ReAct agents with a strict pipeline to prevent financial calculation hallucinations.
- **MCP Tool Servers**: Features decoupled micro-tools (`policy_server`, `receipt_server`, `approval_server`) that pull exact context logically.
- **AI Security Guardrails**: Includes an edge-layer regex/filter guardrail to block Prompt Injection and Jailbreak attempts, saving API costs and securing the backend.
- **Prompt Versioning**: LLM Instructions are entirely decoupled from Python code and maintained in `agent/prompt.yaml` under a `v1` namespace for clean A/B testing capability.
- **Full Observability**: Integrated with LangSmith tracing and local rotating log files (`logs/travel_agent.log`) for complete auditability.

---

## 📂 Project Structure

```text
travel-reimbursement-agent/
├── agent/                   # LangGraph orchestration logic
│   ├── graph.py             # Pipeline wiring
│   ├── guardrails.py        # Input/Output security scanning
│   ├── nodes.py             # Processing steps & LLM routing
│   ├── prompt.yaml          # Versioned external LLM Prompts
│   └── state.py             # TypedDict graph state
├── mcp_servers/             # Local Model Context Protocol Tools
├── data/                    # JSON/CSV/MD Mock Databases & Uploads
├── scripts/                 
│   └── evaluate_agent.py    # Automated 100% test coverage benchmarking
├── api.py                   # FastAPI backend endpoints
├── app.py                   # Streamlit Visualization Frontend
├── docker-compose.yml       # Production deployment architecture

```

---

## 🚀 Running the Agent

You have two ways to run this repository.

### Option 1: Docker (Recommended)
You can launch the entire stack (FastAPI Backend + Streamlit UI) with a single command.
1. Add your Gemini API key to `.env` (`GOOGLE_API_KEY=...`)
2. Run:
```powershell
docker-compose up --build
```
3. Open `http://localhost:8501` to access the main interface.

### Option 2: Local Python Execution
Ensure you have `Python 3.10+` and run:
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

---

## 🧪 Automated Benchmarking

This agent is backed by a deterministic evaluation suite testing 5 core business scenarios. To verify the 100% accuracy score locally, run:
```powershell
python scripts/evaluate_agent.py
```

---


