"""Log Analysis Agent — extracts error patterns and anomalies from service logs.

Responsibilities:
  1. Search log files for error patterns relevant to the incident.
  2. Identify the most significant error messages.
  3. Summarize the log evidence in a structured way.
  4. Flag recurring errors and their frequency.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage

from config import get_settings
from graph.state import AgentState, LogEvidenceItem
from tools.log_search import search_logs, get_error_summary


_LOG_ANALYSIS_SYSTEM_PROMPT = """You are an expert SRE analyzing service logs to find 
the root cause of a production incident.

Given log lines and error summary counts, identify:
1. The most significant error pattern
2. When errors started (if timestamp visible)  
3. The exact error message that best explains the failure
4. Any correlating events before the errors started

Return a JSON object:
{
  "primary_error": "<exact error message or pattern>",
  "error_start_time": "<timestamp or 'unknown'>",
  "error_frequency": "<e.g. '15 errors in 5 seconds'>",
  "log_summary": "<2-3 sentences summarizing what the logs show>",
  "key_signals": ["<signal 1>", "<signal 2>"],
  "confirms_hypothesis": true|false
}"""


def run_log_analysis(state: AgentState) -> dict:
    """Log Analysis agent node — extracts structured error evidence from logs."""
    settings = get_settings()
    now = datetime.now(tz=timezone.utc).isoformat()
    errors = list(state.get("agent_errors", []))
    audit_log = list(state.get("audit_log", []))

    service = state["service"]

    # ── Search logs for relevant errors ───────────────────────────────────
    log_items: list[LogEvidenceItem] = []

    try:
        search_query = f"{service} error timeout connection pool"
        raw_logs = search_logs(
            query=search_query,
            service=service,
            top_k=15,
            errors_only=False,
        )

        for entry in raw_logs:
            log_items.append(LogEvidenceItem(
                timestamp=entry.timestamp,
                level=entry.level,
                service=entry.service,
                message=entry.message,
                error=entry.error,
                source_file=entry.source_file,
            ))

    except Exception as e:
        errors.append(f"Log search failed: {e}")

    # Also check raw_logs attached to the incident report
    raw_attached = state.get("raw_logs") or ""
    if raw_attached and not log_items:
        for line in raw_attached.splitlines()[:20]:
            if line.strip():
                log_items.append(LogEvidenceItem(
                    timestamp=None, level=None, service=service,
                    message=line.strip(), error=None,
                    source_file="incident_report",
                ))

    # ── Get error summary counts ──────────────────────────────────────────
    try:
        error_counts = get_error_summary(service=service)
    except Exception:
        error_counts = {}

    # ── LLM analysis of logs ──────────────────────────────────────────────
    log_analysis_detail = {}
    if log_items:
        llm = ChatGoogleGenerativeAI(
            model=settings.llm_model,
            google_api_key=settings.google_api_key,
            temperature=0.1,
        )

        log_text = "\n".join([
            f"[{e.get('timestamp', '?')}] [{e.get('level', '?')}] "
            f"{e.get('message', '')} {('| ERROR: ' + e['error']) if e.get('error') else ''}"
            for e in log_items[:12]
        ])

        user_content = f"""SERVICE: {service}
INCIDENT: {state['description']}

ERROR COUNTS: {json.dumps(error_counts)}

LOG LINES:
{log_text}

Analyze these logs and return JSON."""

        try:
            response = llm.invoke([
                SystemMessage(content=_LOG_ANALYSIS_SYSTEM_PROMPT),
                HumanMessage(content=user_content),
            ])
            raw_text = response.content.strip()
            if raw_text.startswith("```"):
                raw_text = raw_text.split("```")[1]
                if raw_text.startswith("json"):
                    raw_text = raw_text[4:]
            log_analysis_detail = json.loads(raw_text)
        except Exception as e:
            errors.append(f"Log analysis LLM failed: {e}")
            log_analysis_detail = {"log_summary": f"Log analysis unavailable: {e}"}

    audit_log.append({
        "timestamp": now,
        "event_type": "LOG_ANALYSIS_COMPLETE",
        "actor": "log-analysis-agent",
        "summary": f"Analyzed {len(log_items)} log entries. Error counts: {error_counts}",
        "details": {
            "log_count": len(log_items),
            "error_counts": error_counts,
            "analysis": log_analysis_detail,
        },
    })

    return {
        "log_evidence": log_items,
        "current_node": "diagnosis",
        "audit_log": audit_log,
        "agent_errors": errors,
    }
