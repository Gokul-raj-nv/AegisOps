"""FastAPI observability middleware — automatically traces all HTTP requests.

Adds:
  - OTel spans for every request (method, path, status code, latency)
  - Request ID header propagation (X-Request-ID)
  - Structured logging per request
"""
from __future__ import annotations

import time
import uuid
import logging

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from observability.tracer import get_tracer
from observability.metrics import record_agent_latency

logger = logging.getLogger("aegisops.http")


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """Middleware that wraps every HTTP request in an OTel span."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        tracer = get_tracer()
        start = time.time()

        with tracer.start_as_current_span(
            f"http.{request.method} {request.url.path}"
        ) as span:
            span.set_attribute("http.method", request.method)
            span.set_attribute("http.url", str(request.url))
            span.set_attribute("http.request_id", request_id)

            try:
                response = await call_next(request)
                span.set_attribute("http.status_code", response.status_code)
                if response.status_code >= 500:
                    span.set_status(Status(StatusCode.ERROR))
                response.headers["X-Request-ID"] = request_id
                return response
            except Exception as exc:
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                span.record_exception(exc)
                raise
            finally:
                latency_ms = round((time.time() - start) * 1000, 1)
                span.set_attribute("http.latency_ms", latency_ms)
                logger.info(
                    f"{request.method} {request.url.path} "
                    f"[{getattr(response, 'status_code', 'ERR')}] "
                    f"{latency_ms}ms request_id={request_id}"
                )
