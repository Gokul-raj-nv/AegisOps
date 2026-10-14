"""Triage Agent — first node in the investigation workflow.

Responsibilities:
  1. Parse the incident description and identify the affected service.
  2. Classify the incident type (e.g., performance degradation, DB failure, auth failure).
  3. Assess initial severity and determine investigation priority.
  4. Fetch live metrics to validate the reported severity.
  5. Produce a concise triage summary for downstream agents.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage

from config import get_settings
from graph.state import AgentState, MetricsSnapshot
from tools.metrics import get_service_metrics, get_all_service_metrics


_TRIAGE_SYSTEM_PROMPT = """You are a senior Site Reliability Engineer (SRE) performing 
first-line triage on a production incident.

Your job:
1. Identify the affected service and incident type.
2. Assess whether the reported severity matches the symptoms.
3. Summarize what is known and what still needs investigation.
4. Identify the single most likely failure category from:
   - db_pool_exhaustion
   - high_cpu
   - memory_leak
   - external_dependency_failure
   - network_partition
   - configuration_error
   - replica_overload
   - redis_failure
   - unknown

Output a JSON object with this exact schema:
{
  "affected_service": "<service name>",
  "incident_type": "<one of the categories above>",
  "severity_confirmed": true|false,
  "initial_hypothesis": "<1-2 sentence hypothesis>",
  "triage_summary": "<3-5 sentence summary for the investigation team>",
  "investigation_focus": "<what the next agents should focus on>"
}

Be concise and precise. Do not add fields outside the schema."""


def run_triage(state: AgentState) -> dict:
    """Triage agent node — classifies the incident and fetches live metrics."""
    settings = get_settings()
    now = datetime.now(tz=timezone.utc).isoformat()

    errors = list(state.get("agent_errors", []))
    audit_log = list(state.get("audit_log", []))

    # ── Fetch live service metrics ────────────────────────────────────────
    try:
        # Use incident_mode=True for payment-service during INC-1842 demo
        incident_mode = "payment" in state["service"].lower()
        raw_metrics = get_service_metrics(state["service"], incident_mode=incident_mode)
        metrics_dict = raw_metrics.to_dict()

        metrics: MetricsSnapshot = {
            "service": raw_metrics.service,
            "error_rate": raw_metrics.error_rate,
            "p99_latency_ms": raw_metrics.p99_latency_ms,
            "db_pool_utilization": raw_metrics.db_pool_utilization,
            "db_pool_size": raw_metrics.db_pool_size,
            "db_active_connections": raw_metrics.db_active_connections,
            "cpu_percent": raw_metrics.cpu_percent,
            "healthy": raw_metrics.healthy,
        }
    except Exception as e:
        metrics = None
        metrics_dict = {}
        errors.append(f"Triage: failed to fetch metrics: {e}")

    # ── Build LLM prompt ──────────────────────────────────────────────────
    llm = ChatGoogleGenerativeAI(
        model=settings.llm_model,
        google_api_key=settings.google_api_key,
        temperature=0.1,
    )

    user_content = f"""INCIDENT REPORT
================
Service: {state['service']}
Severity: {state['severity']}
Description: {state['description']}

LIVE METRICS (at investigation time)
=====================================
{json.dumps(metrics_dict, indent=2) if metrics_dict else 'Metrics unavailable'}

Raw logs attached: {"Yes" if state.get('raw_logs') else "No"}

Please triage this incident and return the JSON response."""

    try:
        response = llm.invoke([
            SystemMessage(content=_TRIAGE_SYSTEM_PROMPT),
            HumanMessage(content=user_content),
        ])
        raw_text = response.content.strip()

        # Strip markdown code fences if present
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]

        triage_data = json.loads(raw_text)
        triage_summary = triage_data.get("triage_summary", "Triage complete.")

    except Exception as e:
        errors.append(f"Triage LLM failed: {e}")
        triage_data = {
            "affected_service": state["service"],
            "incident_type": "unknown",
            "triage_summary": f"Triage LLM unavailable. Manual investigation required. Error: {e}",
        }
        triage_summary = triage_data["triage_summary"]

    # ── Record audit event ────────────────────────────────────────────────
    audit_log.append({
        "timestamp": now,
        "event_type": "TRIAGE_COMPLETE",
        "actor": "triage-agent",
        "summary": f"Triage complete for {state['service']}. Incident type: {triage_data.get('incident_type', 'unknown')}",
        "details": triage_data,
    })

    return {
        "metrics": metrics,
        "triage_summary": triage_summary,
        "current_node": "rag_search",
        "audit_log": audit_log,
        "agent_errors": errors,
        "error": None,
    }
