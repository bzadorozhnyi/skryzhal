import time

from prometheus_client import Counter, Histogram
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

REQUEST_COUNT = Counter(
    "http_requests_total", "Total HTTP requests", ["method", "path", "status"]
)
REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path"],
)


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start

        # Route TEMPLATE ("/v1/jobs/{job_id}"), not the resolved URL path —
        # using the raw path would put a unique, cardinality-exploding label
        # value per job_id/template_id into every request metric.
        route = request.scope.get("route")
        path = route.path if route else "unmatched"

        REQUEST_COUNT.labels(
            method=request.method, path=path, status=response.status_code
        ).inc()
        REQUEST_DURATION.labels(method=request.method, path=path).observe(duration)
        return response
