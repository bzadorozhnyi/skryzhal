from collections.abc import Generator
from contextlib import contextmanager

from fastapi import FastAPI
from opentelemetry import propagate, trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Span, SpanKind
from sqlalchemy.ext.asyncio import AsyncEngine

from core.settings import settings

_provider = TracerProvider(
    resource=Resource.create({SERVICE_NAME: settings.TRACING.SERVICE_NAME})
)
_provider.add_span_processor(
    BatchSpanProcessor(
        OTLPSpanExporter(endpoint=settings.TRACING.OTLP_ENDPOINT, insecure=True)
    )
)
trace.set_tracer_provider(_provider)

tracer = trace.get_tracer(settings.TRACING.SERVICE_NAME)


def instrument_sqlalchemy(*, engine: AsyncEngine) -> None:
    # AsyncEngine has no event system of its own — it delegates to the sync
    # Engine it wraps (.sync_engine), which is where these hooks actually live.
    SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)


def instrument_fastapi(*, app: FastAPI) -> None:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(app)


def start_linked_span(
    *, carrier: dict[str, str], name: str, kind: SpanKind = SpanKind.INTERNAL
) -> tuple[Span, dict[str, str]]:
    """Starts a span continuing the trace in `carrier` (from an earlier
    inject_current_carrier() elsewhere), and returns a fresh carrier with
    this new span injected — pass it on to whatever's next in the chain.
    Caller owns the span's lifetime and must call span.end().
    """
    span = tracer.start_span(name, context=propagate.extract(carrier), kind=kind)
    next_carrier: dict[str, str] = {}
    propagate.inject(next_carrier, context=trace.set_span_in_context(span))
    return span, next_carrier


@contextmanager
def linked_span(
    *, carrier: dict[str, str], name: str, kind: SpanKind = SpanKind.INTERNAL
) -> Generator[Span]:
    """Same continuation as start_linked_span, for the common case of one
    span wrapping one block of code — closes automatically on exit.
    """
    with tracer.start_as_current_span(
        name, context=propagate.extract(carrier), kind=kind
    ) as span:
        yield span


def start_linked_span_batch(
    *,
    carriers_by_key: dict[str, dict[str, str]],
    name: str,
    kind: SpanKind = SpanKind.INTERNAL,
) -> tuple[dict[str, Span], dict[str, dict[str, str]]]:
    """Batch version of start_linked_span — one independently-linked span per
    key (each may belong to a different trace), all left open for the caller
    to end() together once the one shared operation they wrap — e.g. a
    single batched network call covering every key — has completed.
    """
    spans: dict[str, Span] = {}
    next_carriers: dict[str, dict[str, str]] = {}
    for key, carrier in carriers_by_key.items():
        spans[key], next_carriers[key] = start_linked_span(
            carrier=carrier, name=name, kind=kind
        )
    return spans, next_carriers


def tag_current_span(**attributes: str) -> None:
    """Sets attributes on whatever span is currently active — e.g. the HTTP
    request span FastAPIInstrumentor already created — so it's searchable by
    a business identifier like job_id without this code owning that span.
    """
    trace.get_current_span().set_attributes(attributes)


def inject_current_carrier() -> dict[str, str]:
    """Captures the current span's context into a plain dict, to hand off
    across a boundary no OTel instrumentation reaches on its own — a DB row
    (the outbox) or an SQS MessageAttributes entry.
    """
    carrier: dict[str, str] = {}
    propagate.inject(carrier)
    return carrier
