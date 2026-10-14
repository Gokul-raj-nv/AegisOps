"""Guardrails package.

Five safety layers that wrap the agent workflow:
  1. confidence_gate  — blocks auto-action below confidence threshold
  2. risk_classifier  — re-validates risk level independently of the agent
  3. permission_checker — enforces user-level access control
  4. output_validator — validates LLM JSON against expected schemas
  5. action_limiter   — rate-limits and audits executed actions
"""
