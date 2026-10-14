"""Diagnosis Agent — synthesizes all gathered evidence into a root cause diagnosis.

Responsibilities:
  1. Synthesize metrics, knowledge evidence, and log evidence.
  2. Produce a root cause with a confidence score (0.0–1.0).
  3. Explain the reasoning chain with specific evidence citations.
  4. Classify the root cause type to drive remediation selection.
  5. Route to remediation (confidence >= MIN_AUTO_ACTION_CONFIDENCE) 
     or escalation (below threshold).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage

from config import get_settings
from graph.state import AgentState, DiagnosisResult


_DIAGNOSIS_SYSTEM_PROMPT = """You are a principal SRE performing root cause analysis 
on a production incident. You have access to live metrics, historical knowledge, 
and log evidence. Your diagnosis must be precise and evidence-backed.

Produce a JSON diagnosis with this exact schema:
{
  "root_cause": "<clear 1-2 sentence statement of the root cause>",
  "root_cause_type": "<one of: db_pool_exhaustion | high_cpu | memory_leak | external_dependency_failure | network_partition | configuration_error | replica_overload | redis_failure | unknown>",
  "suspected_component": "<specific component e.g. 'payment-service PostgreSQL connection pool'>",
  "confidence": <float 0.0-1.0>,
  "reasoning": "<step-by-step chain of reasoning citing specific evidence>",
  "evidence_summary": "<2-3 sentence summary of the key evidence>",
  "evidence_citations": ["<citation 1>", "<citation 2>", ...]
}

Confidence scoring guide:
- 0.90+: Multiple independent sources confirm the exact same failure mode
- 0.75-0.90: Strong evidence from 2+ sources with consistent signals
- 0.60-0.75: Probable cause but some evidence is indirect
- <0.60: Insufficient evidence; escalate to human

Be objective. If evidence is ambiguous, reflect that in confidence score."""


def run_diagnosis(state: AgentState) -> dict:
    """Diagnosis agent node — produces root cause analysis with confidence score."""
    settings = get_settings()
    now = datetime.now(tz=timezone.utc).isoformat()
    errors = list(state.get("agent_errors", []))
    audit_log = list(state.get("audit_log", []))

    # ── Compile all evidence ──────────────────────────────────────────────
    knowledge_evidence = state.get("knowledge_evidence", [])
    log_evidence = state.get("log_evidence", [])
    metrics = state.get("metrics")
    triage_summary = state.get("triage_summary", "")

    # Format knowledge evidence
    knowledge_text = "\n\n".join([
        f"[{e['doc_type'].upper()} | {e['source']} | score={e['relevance_score']:.2f}]\n{e['content'][:600]}"
        for e in knowledge_evidence[:6]
    ]) or "No knowledge evidence retrieved."

    # Format log evidence
    log_text = "\n".join([
        f"[{e.get('timestamp', '?')}] [{e.get('level', '?')}] "
        f"{e.get('message', '')} {('ERROR: ' + e['error']) if e.get('error') else ''}"
        for e in log_evidence[:10]
    ]) or "No log evidence retrieved."

    # Format metrics
    metrics_text = json.dumps(metrics, indent=2) if metrics else "Metrics unavailable."

    # ── Invoke Gemini ─────────────────────────────────────────────────────
    llm = ChatGoogleGenerativeAI(
        model=settings.llm_model,
        google_api_key=settings.google_api_key,
        temperature=0.1,
    )

    user_content = f"""=== INCIDENT ===
Service: {state['service']}
Severity: {state['severity']}
Description: {state['description']}

=== TRIAGE SUMMARY ===
{triage_summary}

=== LIVE METRICS ===
{metrics_text}

=== KNOWLEDGE BASE EVIDENCE ===
{knowledge_text}

=== LOG EVIDENCE ===
{log_text}

Based on all the above evidence, produce a precise root cause diagnosis as JSON."""

    diagnosis: DiagnosisResult | None = None

    try:
        response = llm.invoke([
            SystemMessage(content=_DIAGNOSIS_SYSTEM_PROMPT),
            HumanMessage(content=user_content),
        ])
        raw_text = response.content.strip()
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]

        data = json.loads(raw_text)
        diagnosis = DiagnosisResult(
            root_cause=data.get("root_cause", "Unknown"),
            root_cause_type=data.get("root_cause_type", "unknown"),
            suspected_component=data.get("suspected_component", state["service"]),
            confidence=float(data.get("confidence", 0.5)),
            reasoning=data.get("reasoning", ""),
            evidence_summary=data.get("evidence_summary", ""),
            evidence_citations=data.get("evidence_citations", []),
        )

    except Exception as e:
        errors.append(f"Diagnosis LLM failed: {e}")
        # Fallback: rule-based diagnosis from metrics
        diagnosis = _rule_based_diagnosis(state)

    # ── Determine routing ─────────────────────────────────────────────────
    min_confidence = settings.min_auto_action_confidence
    if diagnosis and diagnosis["confidence"] >= min_confidence:
        next_action = "remediate"
    else:
        next_action = "escalate"

    audit_log.append({
        "timestamp": now,
        "event_type": "DIAGNOSIS_COMPLETE",
        "actor": "diagnosis-agent",
        "summary": (
            f"Root cause: {diagnosis['root_cause'] if diagnosis else 'Unknown'}. "
            f"Confidence: {diagnosis['confidence']:.0%}. "
            f"Routing to: {next_action}."
        ),
        "details": diagnosis,
    })

    return {
        "diagnosis": diagnosis,
        "next_action": next_action,
        "current_node": "remediation" if next_action == "remediate" else "escalation",
        "audit_log": audit_log,
        "agent_errors": errors,
    }


def _rule_based_diagnosis(state: AgentState) -> DiagnosisResult:
    """Fallback rule-based diagnosis when LLM is unavailable."""
    metrics = state.get("metrics")
    service = state["service"]

    if metrics and metrics.get("db_pool_utilization") and metrics["db_pool_utilization"] > 0.90:
        return DiagnosisResult(
            root_cause=(
                f"Database connection pool exhaustion on {service}. "
                f"Pool utilization at {metrics['db_pool_utilization']:.0%} "
                f"({metrics.get('db_active_connections')}/{metrics.get('db_pool_size')} connections used)."
            ),
            root_cause_type="db_pool_exhaustion",
            suspected_component=f"{service} PostgreSQL connection pool",
            confidence=0.82,
            reasoning="Metrics show DB pool utilization above 90% — consistent with QueuePool exhaustion errors.",
            evidence_summary="DB pool utilization critically high. Service unable to acquire new connections.",
            evidence_citations=[f"db_pool_utilization={metrics['db_pool_utilization']:.2f}"],
        )

    return DiagnosisResult(
        root_cause="Unable to determine root cause without LLM. Manual investigation required.",
        root_cause_type="unknown",
        suspected_component=service,
        confidence=0.3,
        reasoning="LLM unavailable; rule-based fallback could not identify a specific pattern.",
        evidence_summary="Insufficient automated analysis. Escalating to human.",
        evidence_citations=[],
    )
