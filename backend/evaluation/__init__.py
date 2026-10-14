"""Evaluation package.

Evaluates the quality of the AegisOps AI pipeline:
  - rag_eval     — RAG retrieval quality (context precision, recall)
  - agent_eval   — Agent output accuracy (diagnosis match, confidence calibration)
  - safety_eval  — Safety checks with adversarial and edge-case inputs
  - cost_tracker — LLM token usage and cost estimation
"""
