"""Cost tracker — tracks LLM token usage and estimates costs.

Instruments all Gemini API calls to accumulate token counts and
report cost per incident investigation.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any


# Gemini 2.5 Flash pricing (USD per 1M tokens, as of mid-2026)
_PRICING: dict[str, dict[str, float]] = {
    "gemini-2.5-flash": {
        "input_per_1m": 0.15,
        "output_per_1m": 0.60,
    },
    "gemini-2.0-flash": {
        "input_per_1m": 0.10,
        "output_per_1m": 0.40,
    },
    "default": {
        "input_per_1m": 0.15,
        "output_per_1m": 0.60,
    },
}


@dataclass
class LLMCallRecord:
    agent_name: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    timestamp: float = field(default_factory=time.time)

    @property
    def cost_usd(self) -> float:
        pricing = _PRICING.get(self.model, _PRICING["default"])
        return (
            self.input_tokens * pricing["input_per_1m"] / 1_000_000
            + self.output_tokens * pricing["output_per_1m"] / 1_000_000
        )


@dataclass
class CostReport:
    incident_id: str
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    total_cost_usd: float
    total_latency_ms: float
    call_count: int
    by_agent: dict[str, dict[str, Any]]


class CostTracker:
    """Thread-safe per-incident cost tracker."""

    def __init__(self) -> None:
        self._records: dict[str, list[LLMCallRecord]] = {}
        self._lock = threading.Lock()

    def record_call(
        self,
        incident_id: str,
        agent_name: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        latency_ms: float,
    ) -> LLMCallRecord:
        record = LLMCallRecord(
            agent_name=agent_name,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
        )
        with self._lock:
            if incident_id not in self._records:
                self._records[incident_id] = []
            self._records[incident_id].append(record)
        return record

    def get_report(self, incident_id: str) -> CostReport:
        with self._lock:
            records = list(self._records.get(incident_id, []))

        by_agent: dict[str, dict[str, Any]] = {}
        for rec in records:
            if rec.agent_name not in by_agent:
                by_agent[rec.agent_name] = {
                    "calls": 0, "input_tokens": 0,
                    "output_tokens": 0, "cost_usd": 0.0, "latency_ms": 0.0,
                }
            by_agent[rec.agent_name]["calls"] += 1
            by_agent[rec.agent_name]["input_tokens"] += rec.input_tokens
            by_agent[rec.agent_name]["output_tokens"] += rec.output_tokens
            by_agent[rec.agent_name]["cost_usd"] += rec.cost_usd
            by_agent[rec.agent_name]["latency_ms"] += rec.latency_ms

        total_input = sum(r.input_tokens for r in records)
        total_output = sum(r.output_tokens for r in records)
        total_cost = sum(r.cost_usd for r in records)
        total_latency = sum(r.latency_ms for r in records)

        return CostReport(
            incident_id=incident_id,
            total_input_tokens=total_input,
            total_output_tokens=total_output,
            total_tokens=total_input + total_output,
            total_cost_usd=round(total_cost, 6),
            total_latency_ms=round(total_latency, 1),
            call_count=len(records),
            by_agent=by_agent,
        )

    def clear(self, incident_id: str) -> None:
        with self._lock:
            self._records.pop(incident_id, None)


# Module-level singleton
_tracker = CostTracker()


def record_llm_call(
    incident_id: str,
    agent_name: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    latency_ms: float,
) -> LLMCallRecord:
    """Record an LLM API call (module-level convenience function)."""
    return _tracker.record_call(
        incident_id=incident_id,
        agent_name=agent_name,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
    )


def get_cost_report(incident_id: str) -> CostReport:
    """Get cost report for an incident (module-level)."""
    return _tracker.get_report(incident_id)


def estimate_tokens(text: str) -> int:
    """Rough token count estimate (4 chars ≈ 1 token)."""
    return max(1, len(text) // 4)
