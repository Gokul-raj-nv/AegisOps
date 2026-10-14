<div align="center">

# AegisOps

### An AI-native, multi-agent platform for investigating production incidents and proposing safe remediation

[![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=111827)](https://react.dev/)
[![LangGraph](https://img.shields.io/badge/LangGraph-multi--agent-1C3C3C)](https://langchain-ai.github.io/langgraph/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Qdrant](https://img.shields.io/badge/Qdrant-vector%20search-DC244C)](https://qdrant.tech/)

</div>

## Overview

AegisOps helps engineers move from alert to an evidence-backed remediation plan without giving an AI unchecked production access. It coordinates specialised agents to triage incidents, collect evidence from logs and knowledge bases, identify likely root causes, and validate proposed actions before routing risky changes to a human for approval.

Every significant decision is recorded in an audit trail so an investigation can be reviewed long after an incident is resolved.

## Highlights

| Area | What AegisOps provides |
| --- | --- |
| **Incident triage** | Classifies the affected service and incident severity as soon as an alert is ingested. |
| **Evidence collection** | Searches operational logs, metrics, and a retrieval-augmented knowledge base. |
| **Multi-agent diagnosis** | Combines specialised triage, RAG, log-analysis, diagnosis, remediation, and validation agents. |
| **Safe remediation** | Produces step-by-step plans with risk classification, expected impact, and rollback guidance. |
| **Human in the loop** | Escalates low-confidence investigations and routes risky remediation for explicit approval. |
| **Traceability** | Persists incidents, agent executions, decisions, approvals, and audit events in PostgreSQL. |
| **Observability** | Instruments the API with OpenTelemetry traces and Prometheus-compatible metrics. |

## How it works

```text
Incident alert
    │
    ▼
Triage ──► Knowledge search ──► Log analysis ──► Diagnosis
                                                   │
                         low confidence ──────────┤──────────► Human escalation
                                                   │
                                                   ▼
                                           Remediation plan
                                                   │
                                                   ▼
                                              Validation
                                                   │
                                                   ▼
                                 Approve / escalate / reject with audit trail
```

## Technology stack

- **Frontend:** React 19, Vite, TypeScript
- **API:** Python 3.12, FastAPI, Pydantic, Uvicorn
- **Agent orchestration:** LangGraph with Google Gemini
- **Retrieval:** Google embeddings and Qdrant vector search
- **Data:** PostgreSQL 16, SQLAlchemy, Alembic
- **Observability:** OpenTelemetry and Prometheus metrics
- **Infrastructure:** Docker Compose, GitHub Actions, Azure Container Apps

## Project structure

```text
AegisOps/
├── backend/
│   ├── agents/           # Triage, RAG, logs, diagnosis, remediation, validation
│   ├── api/              # FastAPI incident endpoints
│   ├── evaluation/       # Agent, RAG, cost, and safety evaluation
│   ├── graph/            # LangGraph investigation workflow and shared state
│   ├── guardrails/       # Risk, confidence, permission, and output checks
│   ├── models/           # SQLAlchemy models and API schemas
│   ├── observability/    # Tracing, metrics, and request middleware
│   ├── rag/              # Ingestion, chunking, embeddings, and retrieval
│   └── tools/            # Log, metric, knowledge, and remediation tools
├── frontend/react-app/   # React operations dashboard
├── data/                 # Synthetic enterprise knowledge-base material
├── infrastructure/       # Docker and OpenTelemetry configuration
├── tests/                # Unit, integration, and evaluation tests
└── docker-compose.yml    # Local service stack
```

## Quick start

### Prerequisites

- Python 3.12 or later
- Node.js 20 or later
- Docker Desktop
- A Google AI API key for Gemini and embeddings

### 1. Configure the environment

Run these commands from the project root in PowerShell:

```powershell
Copy-Item .env.example .env
# Add your GOOGLE_API_KEY to .env

python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 2. Start supporting services and the API

```powershell
docker compose up postgres qdrant -d

Set-Location backend
python -m rag.ingestion
uvicorn main:app --reload
```

The API is now available at:

- API root: [http://127.0.0.1:8000](http://127.0.0.1:8000)
- Interactive documentation: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- Health check: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)

### 3. Start the dashboard

Open a second terminal from the project root:

```powershell
Set-Location frontend/react-app
npm install
npm run dev
```

Vite will print the dashboard URL, normally [http://localhost:5173](http://localhost:5173).

## API at a glance

| Purpose | Endpoint |
| --- | --- |
| Ingest an incident | `POST /incidents` |
| List incidents | `GET /incidents` |
| Retrieve the investigation | `GET /incidents/{id}` |
| Start an investigation | `POST /incidents/{id}/investigate` |
| Retrieve a diagnosis | `GET /incidents/{id}/diagnosis` |
| Approve or reject remediation | `POST /incidents/{id}/approve`, `POST /incidents/{id}/reject` |
| Read the audit trail | `GET /incidents/{id}/audit` |

Investigations run in the background. After triggering one, poll `GET /incidents/{id}` to inspect agent outputs, diagnosis, remediation, approvals, and audit events.

## Quality and safety

The project includes automated checks for backend code, safety evaluation, frontend builds, and Docker image builds. The workflow is defined in `.github/workflows/ci.yml` and runs on pushes and pull requests.

For a local unit-test run:

```powershell
python -m pytest tests/unit -v
```

Never commit a real `GOOGLE_API_KEY`, database password, or production `SECRET_KEY`. Use `.env` locally and configure deployment secrets through the target environment.

## License

MIT
