# HubSpot Master Service - Design Document

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Job State Machine](#job-state-machine)
4. [HubSpot Authentication](#hubspot-authentication)
5. [Pagination Strategy](#pagination-strategy)
6. [Rate Limiting](#rate-limiting)
7. [Retry Behavior](#retry-behavior)
8. [Checkpointing](#checkpointing)
9. [Normalization](#normalization)
10. [MinIO Publishing](#minio-publishing)
11. [HMAC Authentication](#hmac-authentication)
12. [Audit Logging](#audit-logging)
13. [Dead Letter Queue](#dead-letter-queue)
14. [Crash Recovery](#crash-recovery)
15. [Docker Deployment](#docker-deployment)

## Overview

The HubSpot Master Service is an on-demand data extraction service that:
- Extracts CRM data from HubSpot accounts via OAuth-authenticated API calls
- Normalizes raw JSON data into relational-style tables
- Publishes normalized data as Parquet files to MinIO object storage
- Provides HTTP API for job control (start, pause, resume, cancel)
- Tracks job progress and supports crash recovery via PostgreSQL checkpoints
- Authenticates API requests using HMAC-SHA256 signatures

### Design Principles

1. **Stateless execution**: All job state in PostgreSQL, service can restart safely
2. **Checkpoint-driven**: Resume from last successful page, never restart from beginning
3. **Rate limit aware**: Respect HubSpot API limits with exponential backoff
4. **Fault tolerant**: Retry temporary failures, log permanent failures to DLQ
5. **Audit trail**: Log all operations for compliance and debugging
6. **Secure by default**: HMAC authentication, no secrets in logs or version control

## Architecture

### Component Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                     FastAPI Application                      │
├─────────────────────────────────────────────────────────────┤
│  ┌───────────┐  ┌──────────────┐  ┌─────────────────────┐  │
│  │   Scan    │  │Normalization │  │    Maintenance      │  │
│  │  Router   │  │   Router     │  │      Router         │  │
│  └─────┬─────┘  └──────┬───────┘  └──────────┬──────────┘  │
│        │               │                      │             │
│  ┌─────▼───────────────▼──────────────────────▼──────────┐  │
│  │              HMAC Authentication Layer                 │  │
│  └─────┬───────────────┬──────────────────────┬──────────┘  │
└────────┼───────────────┼──────────────────────┼─────────────┘
         │               │                      │
    ┌────▼────┐    ┌─────▼──────┐        ┌─────▼──────┐
    │Extraction│    │Normalization│        │  Audit    │
    │ Service │    │  Service    │        │ Service   │
    └────┬────┘    └─────┬──────┘        └─────┬──────┘
         │               │                      │
    ┌────▼────────┬──────▼──────────────────────▼─────────┐
    │              PostgreSQL Database                     │
    │  - jobs            - audit_logs                      │
    │  - job_checkpoints - failed_external_calls           │
    └──────────────────────────────────────────────────────┘
         │               
    ┌────▼──────────┐  ┌─────────────┐
    │  HubSpot API  │  │    MinIO    │
    │  (OAuth v3)   │  │   Storage   │
    └───────────────┘  └─────────────┘
```

### Layer Responsibilities

#### API Layer (`apps/api/`)
- HTTP request handling
- HMAC signature verification
- Request/response serialization
- Error handling and status codes

#### Service Layer (`apps/services/`)
- Business logic orchestration
- Job lifecycle management
- Data transformation
- State transitions

#### Client Layer (`apps/clients/`)
- External service communication
- OAuth token management
- API request construction
- Response parsing

#### Utility Layer (`apps/utils/`)
- Rate limiting logic
- Retry with exponential backoff
- HMAC signature computation
- Dead letter queue writes

#### Data Layer (`apps/models/`)
- Database schema definition
- ORM mappings
- Query helpers

## Job State Machine

### States

```
PENDING
   │
   ▼
RUNNING ◄───────┐
   │            │
   ├─────► PAUSED
   │            │
   │            ▼
   │        RESUMING
   │
   ├─────► NORMALIZING
   │            │
   │            ▼
   │     UPLOADING_TO_MINIO
   │            │
   │            ▼
   ├─────► COMPLETED
   │
   ├─────► CANCELLED
   │
   ├─────► FAILED
   │
   └─────► CRASHED
```

### State Descriptions

| State | Description | Can Transition To |
|-------|-------------|-------------------|
| PENDING | Job created, not started | RUNNING |
| RUNNING | Actively extracting from HubSpot | PAUSED, NORMALIZING, COMPLETED, FAILED, CANCELLED, CRASHED |
| PAUSED | User paused, waiting to resume | RESUMING |
| RESUMING | Resuming from pause | RUNNING |
| NORMALIZING | Transforming raw data | UPLOADING_TO_MINIO, FAILED |
| UPLOADING_TO_MINIO | Uploading to object storage | COMPLETED, FAILED |
| COMPLETED | Successfully finished | (terminal) |
| FAILED | Failed due to error | (terminal) |
| CANCELLED | Cancelled by user | (terminal) |
| CRASHED | Detected as crashed | RESUMING |

### State Transition Rules

1. **PENDING → RUNNING**: Automatic on job creation
2. **RUNNING → PAUSED**: User requests pause, waits for page completion
3. **PAUSED → RESUMING**: User requests resume
4. **RESUMING → RUNNING**: Resume initialization complete
5. **RUNNING → NORMALIZING**: All object types extracted
6. **NORMALIZING → UPLOADING_TO_MINIO**: Normalization complete
7. **UPLOADING_TO_MINIO → COMPLETED**: All files uploaded
8. **Any → FAILED**: Unrecoverable error occurs
9. **RUNNING → CANCELLED**: User requests cancel, waits for page completion
10. **RUNNING → CRASHED**: Heartbeat timeout detected

## HubSpot Authentication

### OAuth 2.0 Flow

#### Initial Authorization
```
1. User visits authorization URL:
   https://app.hubspot.com/oauth/authorize?
     client_id=<CLIENT_ID>&
     redirect_uri=<REDIRECT_URI>&
     scope=<SCOPES>

2. User authorizes app

3. HubSpot redirects to:
   <REDIRECT_URI>?code=<AUTHORIZATION_CODE>

4. Service exchanges code for tokens:
   POST /oauth/v1/token
   {
     "grant_type": "authorization_code",
     "client_id": "<CLIENT_ID>",
     "client_secret": "<CLIENT_SECRET>",
     "redirect_uri": "<REDIRECT_URI>",
     "code": "<AUTHORIZATION_CODE>"
   }

5. Response:
   {
     "access_token": "...",
     "refresh_token": "...",
     "expires_in": 21600
   }
```

#### Token Refresh

```
POST /oauth/v1/token
{
  "grant_type": "refresh_token",
  "client_id": "<CLIENT_ID>",
  "client_secret": "<CLIENT_SECRET>",
  "refresh_token": "<REFRESH_TOKEN>"
}
```

### Token Management

- **Storage**: Encrypted in `jobs` table
- **Expiry tracking**: `token_expires_at` column
- **Automatic refresh**: Before API calls if token expired
- **Retry on 401**: Refresh token and retry once

### Security Considerations

1. **Never log tokens**: Scrubbed from all logs and DLQ
2. **Encrypt at rest**: Use database encryption for token columns
3. **Rotate secrets**: Support secret rotation without downtime
4. **Scope minimization**: Request only required scopes

## Pagination Strategy

### HubSpot Cursor Pagination

HubSpot API uses cursor-based pagination:

```json
// First request
GET /crm/v3/objects/contacts?limit=100

// Response
{
  "results": [...],
  "paging": {
    "next": {
      "after": "NTI1Cg%3D%3D",
      "link": "..."
    }
  }
}

// Second request
GET /crm/v3/objects/contacts?limit=100&after=NTI1Cg%3D%3D

// Last page response (no paging.next)
{
  "results": [...],
  "paging": {}
}
```

### Implementation

```python
async def extract_object_type(object_type: str):
    checkpoint = load_checkpoint(object_type)
    cursor = checkpoint.cursor
    
    while True:
        # Fetch page
        page = await api.get_page(
            object_type=object_type,
            after_cursor=cursor
        )
        
        # Process records
        process_records(page.results)
        
        # Save checkpoint
        cursor = page.paging.next.after
        save_checkpoint(object_type, cursor, records_count)
        
        # Check for completion
        if not cursor:
            break
```

### Checkpoint Format

```python
{
    "job_id": 123,
    "object_type": "contacts",
    "cursor": "NTI1Cg%3D%3D",
    "records_processed": 500,
    "last_updated_at": "2026-08-12T10:30:00Z"
}
```

### Edge Cases

1. **Empty result set**: First page has no results
2. **Single page**: No `paging.next` on first page
3. **Cursor invalidation**: Cursor expires, restart from beginning
4. **Duplicate records**: HubSpot may return duplicates, deduplicate in normalization

## Rate Limiting

### HubSpot API Limits

- **Burst limit**: 100 requests per 10 seconds
- **Daily limit**: 500,000 requests per day (varies by subscription)
- **Rate limit response**: HTTP 429 with `Retry-After` header

### Two-Tier Rate Limiting

#### 1. Proactive Rate Limiting

Track requests in sliding window:

```python
class RateLimiter:
    def __init__(self):
        self.request_times = []
        self.burst_limit = 100
        self.window_seconds = 10
    
    async def wait_if_needed(self):
        now = time.time()
        # Remove old requests
        self.request_times = [
            t for t in self.request_times
            if now - t < self.window_seconds
        ]
        
        # Wait if at limit
        if len(self.request_times) >= self.burst_limit:
            wait_time = self.window_seconds - (now - self.request_times[0])
            await asyncio.sleep(wait_time)
        
        # Record request
        self.request_times.append(now)
```

#### 2. Reactive 429 Handling

When HubSpot returns 429:

```python
async def make_request():
    response = await http_client.get(url)
    
    if response.status_code == 429:
        retry_after = int(response.headers.get("Retry-After", 5))
        await asyncio.sleep(retry_after)
        return await make_request()  # Retry same request
    
    return response
```

### Key Differences from Generic Retries

- **429 is NOT a failure**: Don't count toward retry limit
- **Always retry**: 429 requires retry, not optional
- **Use Retry-After**: Honor the header value
- **Clear rate state**: Reset rate limiter after 429

## Retry Behavior

### Retryable Errors

```python
RETRYABLE_ERRORS = [
    # Connection errors
    httpx.TimeoutException,
    httpx.ConnectError,
    httpx.ReadError,
    
    # Server errors
    HTTP 500,  # Internal Server Error
    HTTP 502,  # Bad Gateway
    HTTP 503,  # Service Unavailable
    HTTP 504,  # Gateway Timeout
]

NON_RETRYABLE_ERRORS = [
    HTTP 429,  # Rate limit (handled separately)
    HTTP 4xx,  # Client errors (except 429)
    HTTP 2xx,  # Success (no retry needed)
]
```

### Exponential Backoff with Jitter

```python
delays = [1, 2, 4]  # Base delays in seconds
jitter = 0.5        # 50% jitter

# Attempt 1: delay = 1 + random(0, 0.5) = 1.0 - 1.5s
# Attempt 2: delay = 2 + random(0, 1.0) = 2.0 - 3.0s
# Attempt 3: delay = 4 + random(0, 2.0) = 4.0 - 6.0s
# Attempt 4: EXHAUSTED → Dead Letter Queue
```

### Retry Logic

```python
async def retry_with_backoff(func, max_retries=3):
    for attempt in range(max_retries + 1):
        try:
            return await func()
        except Exception as e:
            if not is_retryable(e):
                raise  # Non-retryable, fail immediately
            
            if attempt >= max_retries:
                raise ExhaustedRetriesError()
            
            delay = calculate_delay(attempt)
            await asyncio.sleep(delay)
```

### Retry vs Rate Limit Comparison

| Aspect | Retry | Rate Limit (429) |
|--------|-------|------------------|
| Trigger | Timeout, 5xx | HTTP 429 |
| Count limit | Yes (3 retries) | No (always retry) |
| Delay | Exponential backoff | Retry-After header |
| State | Independent | Clears rate limiter |
| DLQ | Yes if exhausted | No |

## Checkpointing

### Purpose

Checkpoints enable:
1. **Pause/Resume**: Stop and restart without data loss
2. **Crash Recovery**: Resume from last known good state
3. **Progress Tracking**: Monitor extraction progress
4. **Idempotency**: Avoid duplicate extractions

### Checkpoint Schema

```sql
CREATE TABLE job_checkpoints (
    id SERIAL PRIMARY KEY,
    job_id INTEGER REFERENCES jobs(id),
    object_type VARCHAR(100),
    cursor VARCHAR(500),
    records_processed INTEGER,
    last_updated_at TIMESTAMP,
    UNIQUE(job_id, object_type)
);
```

### Checkpoint Lifecycle

```
1. Job starts
   └─> Create checkpoint for each object_type
       (cursor=NULL, records_processed=0)

2. Page fetched successfully
   └─> Update checkpoint
       (cursor=next_cursor, records_processed+=page_size)

3. Pause requested
   └─> Finish current page
   └─> Save final checkpoint
   └─> Set status=PAUSED

4. Resume requested
   └─> Load checkpoint
   └─> Continue from checkpoint.cursor

5. Job completes
   └─> Checkpoint remains for audit trail
```

### Checkpoint Guarantees

- **At-least-once delivery**: May process same page twice if crash between fetch and checkpoint
- **No data loss**: Always resume from last successful checkpoint
- **Atomic updates**: Checkpoint update in same transaction as record processing

### Example Flow

```
Initial state:
  checkpoint(job=1, type="contacts", cursor=NULL, records=0)

Page 1 fetched (100 records, next_cursor="ABC"):
  checkpoint(job=1, type="contacts", cursor="ABC", records=100)

Page 2 fetched (100 records, next_cursor="DEF"):
  checkpoint(job=1, type="contacts", cursor="DEF", records=200)

CRASH occurs here

Resume:
  Load checkpoint → cursor="DEF", records=200
  Continue from cursor="DEF"
  No duplicate records in final output
```

## Normalization

### Raw Data → Normalized Tables

HubSpot returns nested JSON:

```json
{
  "id": "123",
  "properties": {
    "email": "test@example.com",
    "firstname": "John",
    "lastname": "Doe",
    "hs_object_id": "123"
  },
  "createdAt": "2026-01-01T00:00:00Z",
  "updatedAt": "2026-08-12T00:00:00Z"
}
```

Normalized to flat table:

```
contacts (Parquet)
├── id: string
├── email: string
├── firstname: string
├── lastname: string
├── created_at: timestamp
├── updated_at: timestamp
└── _extracted_at: timestamp
```

### Normalizers

Each object type has a dedicated normalizer:

#### ContactNormalizer
```python
class ContactNormalizer:
    def normalize(self, raw_contacts: List[Dict]) -> pd.DataFrame:
        records = []
        for contact in raw_contacts:
            records.append({
                "id": contact["id"],
                "email": contact["properties"].get("email"),
                "firstname": contact["properties"].get("firstname"),
                "lastname": contact["properties"].get("lastname"),
                "created_at": contact["createdAt"],
                "updated_at": contact["updatedAt"],
                "_extracted_at": datetime.utcnow(),
            })
        return pd.DataFrame(records)
```

#### DealNormalizer

Produces multiple tables:

1. **deals**: Core deal properties
2. **deal_line_items**: Line items if present
3. **deal_associations**: Associations to other objects

```python
class DealNormalizer:
    def normalize(self, raw_deals: List[Dict]) -> Dict[str, pd.DataFrame]:
        deals = []
        line_items = []
        associations = []
        
        for deal in raw_deals:
            # Main deal record
            deals.append({...})
            
            # Line items
            if "line_items" in deal:
                line_items.extend([...])
            
            # Associations
            if "associations" in deal:
                associations.extend([...])
        
        return {
            "deals": pd.DataFrame(deals),
            "deal_line_items": pd.DataFrame(line_items),
            "deal_associations": pd.DataFrame(associations),
        }
```

### Schema Evolution

- **Unknown properties**: Stored in `_extra_properties` JSON column
- **New properties**: Automatically included in next schema version
- **Removed properties**: Null in output
- **Type changes**: Stored as string, cast at query time

### Output Format

**Parquet** is the primary format:
- Columnar storage (efficient compression)
- Schema embedded in file
- Fast query performance
- Supported by Spark, Pandas, DuckDB, etc.

```python
df.to_parquet(
    "contacts.parquet",
    engine="pyarrow",
    compression="snappy",
    index=False,
)
```

## MinIO Publishing

### Directory Structure

```
hubspot/
  {table_name}/
    glynac_organization_id={org_id}/
      processing_date={date}/
        {table_name}.parquet
```

Example:
```
hubspot/
  contacts/
    glynac_organization_id=org_123/
      processing_date=2026-08-12/
        contacts.parquet
  companies/
    glynac_organization_id=org_123/
      processing_date=2026-08-12/
        companies.parquet
```

### Upload Process

```python
async def upload_normalized_data(
    scan_id: int,
    organization_id: str,
    processing_date: datetime,
    tables: Dict[str, str],  # table_name -> local_path
):
    for table_name, local_path in tables.items():
        object_key = (
            f"hubspot/{table_name}/"
            f"glynac_organization_id={organization_id}/"
            f"processing_date={processing_date.strftime('%Y-%m-%d')}/"
            f"{table_name}.parquet"
        )
        
        await minio_client.upload_file(
            local_path=local_path,
            object_key=object_key,
            content_type="application/parquet",
        )
```

### Retry Strategy

MinIO uploads use the same retry logic as HubSpot calls:
- Retry on connection errors, timeouts
- Exponential backoff with jitter
- Write to DLQ if exhausted

### Partitioning

Data is partitioned by:
1. **Organization ID**: Multi-tenant isolation
2. **Processing Date**: Time-based partitioning for incremental loads

This enables efficient queries:
```sql
-- Query single organization
SELECT * FROM contacts
WHERE glynac_organization_id = 'org_123'

-- Query date range
SELECT * FROM contacts
WHERE processing_date BETWEEN '2026-08-01' AND '2026-08-31'
```

## HMAC Authentication

### Purpose

Authenticate requests from Coordinator system using shared secrets (no OAuth needed for service-to-service).

### Signature Computation

#### Canonical String

```
METHOD\nPATH\nTIMESTAMP\nNONCE\nBODY_HASH
```

Example:
```
POST\n/api/scan/start\n1691840000\nuuid-1234\na3f5b...
```

#### Signature

```python
signature = HMAC-SHA256(secret_key, canonical_string)
```

### Request Headers

```
X-HS-Signature: <hex-encoded-hmac-sha256>
X-HS-Timestamp: <unix-timestamp>
X-HS-Client-ID: <client-identifier>
X-HS-Nonce: <unique-random-value>
```

### Verification Process

```python
async def verify_hmac_signature(request: Request):
    # 1. Extract headers
    signature = request.headers["X-HS-Signature"]
    timestamp = request.headers["X-HS-Timestamp"]
    client_id = request.headers["X-HS-Client-ID"]
    nonce = request.headers["X-HS-Nonce"]
    
    # 2. Verify client exists
    client_config = get_client_config(client_id)
    if not client_config:
        raise HTTPException(401, "Invalid client")
    
    # 3. Verify timestamp freshness
    if abs(time.time() - int(timestamp)) > 300:  # 5 minutes
        raise HTTPException(401, "Signature expired")
    
    # 4. Compute expected signature
    body = await request.body()
    body_hash = hashlib.sha256(body).hexdigest()
    canonical = f"{request.method}\n{request.url.path}\n{timestamp}\n{nonce}\n{body_hash}"
    expected = hmac.new(client_config["secret"].encode(), canonical.encode(), hashlib.sha256).hexdigest()
    
    # 5. Compare signatures
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(401, "Invalid signature")
    
    # 6. Check nonce (TODO: implement replay protection)
    
    return client_id, client_config["role"]
```

### Client Roles

| Client ID | Role | Permissions |
|-----------|------|-------------|
| coordinator | COORDINATOR | Full access (read + write) |
| engineer | ENGINEER | Read-only access |

### Authorization

```python
@router.post("/api/scan/start")
async def start_scan(
    request: Request,
    auth: Tuple[str, str] = Depends(require_role([ClientRole.COORDINATOR]))
):
    client_id, role = auth
    # Only COORDINATOR can start scans
    ...
```

### Security Properties

- **Integrity**: Body tampering detected via body hash
- **Authentication**: Only clients with secret can sign
- **Freshness**: Timestamp prevents replay after 5 minutes
- **Non-repudiation**: Signature proves client sent request

## Audit Logging

### Purpose

Track all operations for:
- Security compliance
- Debugging
- Performance monitoring
- User behavior analysis

### Audit Schema

```sql
CREATE TABLE audit_logs (
    id SERIAL PRIMARY KEY,
    event_category VARCHAR(50),      -- AUTHENTICATION, JOB_LIFECYCLE, etc.
    event_type VARCHAR(100),          -- login_success, job_created, etc.
    actor_client_id VARCHAR(255),     -- Who performed the action
    actor_role VARCHAR(50),           -- coordinator, engineer, etc.
    organization_id VARCHAR(255),     -- Which organization
    resource_type VARCHAR(100),       -- job, scan, etc.
    resource_id VARCHAR(255),         -- Resource identifier
    http_method VARCHAR(10),          -- GET, POST, etc.
    endpoint VARCHAR(500),            -- /api/scan/start
    request_ip VARCHAR(45),           -- Client IP
    status_code INTEGER,              -- HTTP status
    outcome VARCHAR(20),              -- SUCCESS, FAILURE
    severity VARCHAR(20),             -- INFO, WARNING, ERROR
    error_detail TEXT,                -- Error message if failed
    extra_metadata JSONB,             -- Additional context
    created_at TIMESTAMP              -- When it happened
);
```

### Event Categories

```python
class AuditEventCategory(str, enum.Enum):
    AUTHENTICATION = "AUTHENTICATION"      # Login, token refresh
    AUTHORIZATION = "AUTHORIZATION"        # Permission checks
    JOB_LIFECYCLE = "JOB_LIFECYCLE"       # Job state changes
    DATA_EXTRACTION = "DATA_EXTRACTION"   # HubSpot API calls
    DATA_NORMALIZATION = "DATA_NORMALIZATION"  # Transform operations
    DATA_UPLOAD = "DATA_UPLOAD"           # MinIO uploads
    SYSTEM = "SYSTEM"                     # System events
    API_REQUEST = "API_REQUEST"           # HTTP requests
```

### Logging Examples

#### Authentication Success
```python
audit_service.log(
    event_category=AuditEventCategory.AUTHENTICATION,
    event_type="hmac_auth_success",
    actor_client_id="coordinator",
    actor_role="COORDINATOR",
    endpoint="/api/scan/start",
    http_method="POST",
    request_ip="10.0.1.5",
    outcome=AuditOutcome.SUCCESS,
    severity=AuditSeverity.INFO,
)
```

#### Job State Change
```python
audit_service.log(
    event_category=AuditEventCategory.JOB_LIFECYCLE,
    event_type="job_status_changed",
    actor_client_id="coordinator",
    organization_id="org_123",
    resource_type="job",
    resource_id=str(job.id),
    outcome=AuditOutcome.SUCCESS,
    severity=AuditSeverity.INFO,
    extra_metadata={
        "old_status": "RUNNING",
        "new_status": "COMPLETED",
        "records_processed": 1000,
    },
)
```

#### Failed API Call
```python
audit_service.log(
    event_category=AuditEventCategory.DATA_EXTRACTION,
    event_type="hubspot_api_error",
    organization_id="org_123",
    resource_type="job",
    resource_id=str(job.id),
    outcome=AuditOutcome.FAILURE,
    severity=AuditSeverity.ERROR,
    error_detail=str(exception),
    extra_metadata={
        "object_type": "contacts",
        "attempt": 3,
    },
)
```

### Best Practices

1. **Non-blocking**: Audit writes should not fail main operation
2. **Scrubbed**: Never log secrets or sensitive data
3. **Structured**: Use metadata JSON for complex data
4. **Queryable**: Index on common query fields (org_id, created_at)
5. **Retention**: Archive/delete old logs per policy

## Dead Letter Queue

### Purpose

Store failed external calls that have exhausted retries for:
- Manual investigation
- Retry after fixing root cause
- Metrics and alerting

### DLQ Schema

```sql
CREATE TABLE failed_external_calls (
    id SERIAL PRIMARY KEY,
    target_service VARCHAR(100),      -- hubspot, minio, etc.
    operation VARCHAR(255),           -- get_page, upload_file, etc.
    payload TEXT,                     -- Request payload (scrubbed)
    attempts INTEGER,                 -- Number of retry attempts
    error_message TEXT,               -- Last error message
    error_details JSONB,              -- Exception details
    organization_id VARCHAR(255),     -- Context
    scan_id INTEGER,                  -- Context
    created_at TIMESTAMP              -- When it failed
);
```

### Sensitive Data Scrubbing

Before writing to DLQ, scrub sensitive fields:

```python
SENSITIVE_FIELDS = {
    "client_secret",
    "access_token",
    "refresh_token",
    "hmac_secret",
    "password",
}

def scrub_sensitive_data(payload: Dict) -> Dict:
    scrubbed = {}
    for key, value in payload.items():
        if any(sensitive in key.lower() for sensitive in SENSITIVE_FIELDS):
            scrubbed[key] = "[REDACTED]"
        else:
            scrubbed[key] = scrub_sensitive_data(value) if isinstance(value, dict) else value
    return scrubbed
```

### Writing to DLQ

```python
def write_to_dlq(
    db: Session,
    target_service: str,
    operation: str,
    payload: Dict,
    attempts: int,
    error: Exception,
    organization_id: str = None,
    scan_id: int = None,
):
    try:
        scrubbed_payload = scrub_sensitive_data(payload)
        
        dlq_record = FailedExternalCall(
            target_service=target_service,
            operation=operation,
            payload=json.dumps(scrubbed_payload),
            attempts=attempts,
            error_message=str(error),
            organization_id=organization_id,
            scan_id=scan_id,
        )
        
        db.add(dlq_record)
        db.commit()
    except Exception as dlq_error:
        # Don't let DLQ failure break main flow
        logger.error(f"Failed to write to DLQ: {dlq_error}")
```

### DLQ Monitoring

Query DLQ for alerts:

```sql
-- Failed calls in last hour
SELECT target_service, operation, COUNT(*)
FROM failed_external_calls
WHERE created_at > NOW() - INTERVAL '1 hour'
GROUP BY target_service, operation;

-- Failed calls for specific organization
SELECT *
FROM failed_external_calls
WHERE organization_id = 'org_123'
ORDER BY created_at DESC
LIMIT 10;
```

## Crash Recovery

### Detection

Jobs are considered crashed if:
```python
last_heartbeat < current_time - timeout_threshold
AND status = 'RUNNING'
```

Default timeout: 30 minutes

### Heartbeat Update

```python
def _execute_scan(job_id: int):
    while extracting:
        # Update heartbeat every page
        update_heartbeat(job_id, datetime.utcnow())
        
        # Fetch and process page
        page = await fetch_page()
        process_page(page)
```

### Detection Endpoint

```http
POST /api/maintenance/detect-crashed
{
  "timeout_minutes": 30
}

Response:
{
  "crashed_jobs": [123, 456],
  "count": 2
}
```

### Recovery Process

```
1. Detect crashed job
   └─> Mark as CRASHED

2. User resumes crashed job
   └─> Load checkpoints for all object types
   └─> Resume extraction from last cursor
   └─> Continue normally

3. Job completes successfully
```

### Checkpoint Protection

Checkpoints protect against:
- Service restart
- Container crash
- Network partition
- Database disconnect (if transaction committed)

Checkpoints do NOT protect against:
- Database crash before commit
- Corrupted cursor
- HubSpot API breaking changes

## Docker Deployment

### Services

```yaml
services:
  api:           # FastAPI application
  postgres:      # PostgreSQL database
  minio:         # Object storage
```

### Networking

All services on `hubspot-network` bridge:
- Service discovery by container name
- Internal DNS resolution
- Isolated from host network

### Volumes

```yaml
postgres-data:  # Persistent PostgreSQL data
minio-data:     # Persistent MinIO data
```

### Health Checks

```yaml
postgres:
  healthcheck:
    test: pg_isready -U hubspot_user -d hubspot_master
    interval: 10s
    retries: 5

minio:
  healthcheck:
    test: curl -f http://localhost:9000/minio/health/live
    interval: 30s
    retries: 3
```

### Environment Variables

Passed via docker-compose.yml:
```yaml
environment:
  - DATABASE_URL=postgresql://hubspot_user:...@postgres:5432/hubspot_master
  - MINIO_ENDPOINT=minio:9000
  - HUBSPOT_CLIENT_ID=${HUBSPOT_CLIENT_ID}
```

### Scaling Considerations

**Current limitations** (single-instance design):
- In-memory pause/cancel flags
- No distributed locking
- No job queue

**Future improvements**:
- Redis for shared state
- Celery/RQ for job queue
- Database-based locking for multi-instance

### Production Deployment

For production, consider:
1. **Secrets management**: Use Docker secrets or Kubernetes secrets
2. **Resource limits**: Set CPU/memory limits
3. **Logging**: Centralized logging (ELK, Splunk)
4. **Monitoring**: Prometheus metrics, health checks
5. **Backups**: Automated PostgreSQL backups
6. **High availability**: Multiple replicas with load balancer

---

## Conclusion

This design provides a robust, fault-tolerant system for extracting HubSpot data with:
- Comprehensive error handling
- Crash recovery via checkpoints
- Rate limit awareness
- Secure authentication
- Complete audit trail
- Clean separation of concerns

The architecture supports production deployment while remaining simple enough for development and testing.
