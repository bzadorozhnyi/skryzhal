# Skryzhal

Async document-generation backend: Typst templates + JSON data → PDF. FastAPI + PostgreSQL + SQLAlchemy/Alembic, with S3/SQS (via LocalStack) for storage and queueing. Three independent processes — `api`, `worker`, `relay` — coordinated only through the database and the queue, never directly.

## Architecture

```mermaid
flowchart LR
    Client -->|HTTP| API[api]
    API -->|read/write| DB[(PostgreSQL)]
    Worker[worker] -->|claim / write result| DB
    Relay[relay] -->|claim outbox events| DB
    Relay -->|publish| SQS[(SQS queue)]
    Worker -->|receive / delete| SQS
    API -->|presigned URLs| S3[(S3)]
    Worker -->|download template<br/>upload result| S3
```

## Job lifecycle — from request to completion

```mermaid
sequenceDiagram
    autonumber
    actor Client
    participant API as api (FastAPI)
    participant DB as PostgreSQL
    participant Relay as relay
    participant SQS
    participant Worker as worker
    participant S3

    Client->>API: PUT /v1/jobs/{job_id}
    API->>DB: SELECT templates (exists?)
    API->>DB: SELECT render_jobs (idempotency check)
    API->>DB: INSERT render_jobs (status=PENDING)
    API->>DB: INSERT outbox_events (JOB_CREATED, payload: job_id + trace_carrier)
    Note over API,DB: one transaction — both inserts commit together, or neither does
    API-->>Client: 201 { status: PENDING }

    loop every ~2s (or immediately if there's a backlog)
        Relay->>DB: SELECT outbox_events WHERE published_at IS NULL<br/>FOR UPDATE SKIP LOCKED LIMIT 10
        Relay->>SQS: send_message_batch(MessageBody={job_id}, MessageAttributes={traceparent})
        Relay->>DB: UPDATE outbox_events SET published_at=now(), dispatch_id=...
    end

    loop long-poll, ~20s
        Worker->>SQS: receive_message (MessageAttributeNames=All)
        SQS-->>Worker: message
        Worker->>DB: UPDATE render_jobs SET status=PROCESSING, locked_until=now()+25s<br/>WHERE status=PENDING OR (status=PROCESSING AND locked_until<now())
        Note over Worker,DB: claim commits immediately — separate from the render work below
        par heartbeat, every 20s
            Worker->>SQS: change_message_visibility(+30s)
            Worker->>DB: UPDATE render_jobs SET locked_until=now()+25s<br/>WHERE locked_until=$held_value
        and render
            Worker->>S3: GetObject (template)
            Worker->>Worker: typst compile
            Worker->>S3: PutObject (result.pdf)
            Worker->>DB: UPDATE render_jobs SET status=COMPLETED, result_s3_key=...<br/>WHERE locked_until=$held_value
        end
        Worker->>SQS: delete_message
    end

    Client->>API: GET /v1/jobs/{job_id}
    API->>DB: SELECT render_jobs
    Note over API,S3: if COMPLETED — presigned URL is signed locally,<br/>no network round-trip to S3
    API->>S3: generate_presigned_url (get_object)
    API-->>Client: 200 { status: COMPLETED, get_url: <presigned S3 URL> }
```

### Status transitions

```mermaid
stateDiagram-v2
    [*] --> PENDING: create_job
    PENDING --> PROCESSING: worker claims (lease acquired)
    PROCESSING --> COMPLETED: render succeeds
    PROCESSING --> FAILED: template missing / typst compile error
    PROCESSING --> PENDING: transient failure (S3/DB hiccup) — reverts for retry
    PROCESSING --> PROCESSING: lease expired, reclaimed by another worker
    FAILED --> PENDING: POST /jobs/{id}/retry
    COMPLETED --> [*]
```

## Reliability mechanisms

| Mechanism | Where | Problem it solves |
|---|---|---|
| Idempotent create | `PUT /jobs/{id}` (client-supplied id) | Retried requests don't create duplicate jobs |
| Transactional outbox | `outbox_events` table | Job row and "publish to SQS" commit atomically — no dual-write gap |
| Retry + exponential backoff | `worker.py` | Transient render failures (S3/DB hiccups) don't fail permanently |
| Dead-letter queue | SQS redrive policy | Poison messages don't loop forever |
| Lease + fencing | `render_jobs.locked_until` | A worker that dies mid-render (any cause — SIGKILL, OOM, crash) doesn't leave the job stuck; a "zombie" worker that resurfaces can't overwrite a job someone else already reclaimed |
| Dead man's switch | Prometheus heartbeat gauges + Alertmanager | Detects a hung main loop, not just a dead process |

### Lease + fencing, in detail

A claim on `render_jobs` is only valid until `locked_until` — past that, it's up for grabs by anyone. The worker renews it periodically (in lockstep with the SQS visibility timeout, always slightly shorter — `SQS.LEASE_SECONDS = VISIBILITY_TIMEOUT_SECONDS - LEASE_BUFFER_SECONDS`), so a redelivered SQS message never finds a claim that's still "validly" held.

`locked_until` doubles as a fencing token: every write past the initial claim (lease renewal, or the final COMPLETED/FAILED/PENDING transition) is conditioned on `locked_until` still matching the exact value the worker was handed. If another worker has since reclaimed the job, that value has changed, and the write silently fails — the original ("zombie") worker's stale result is discarded instead of corrupting whoever's now the real owner.

```mermaid
sequenceDiagram
    autonumber
    participant SQS
    participant A as worker (dies mid-render)
    participant DB as PostgreSQL
    participant B as worker (any instance)

    A->>DB: claim: status=PROCESSING, locked_until=now()+25s
    Note over A: process dies — SIGKILL, OOM, host failure, no warning
    Note over SQS: visibility timeout (30s) expires — nothing extended it
    SQS-->>B: message redelivered
    B->>DB: claim: WHERE status=PENDING OR (status=PROCESSING AND locked_until<now())
    Note over DB: locked_until already expired (25s < 30s by design) — reclaimed
    B->>DB: renders normally, writes COMPLETED

    Note over A: if A somehow resurfaces and tries to write its stale result:
    A->>DB: UPDATE ... WHERE locked_until=$A's_old_value
    DB-->>A: 0 rows updated — rejected, A's lease is stale
```

## Local development

Everything runs against LocalStack — no real AWS account needed.

```bash
docker compose up -d
```

Services: `api` (`:8000`), `worker`, `relay`, `db` (`:5432`), `localstack` (`:4566`). Observability: Grafana (`:3001`, anonymous access) with Loki (logs), Prometheus (metrics, `:9090`), Alertmanager (`:9093`), and Tempo (traces).
