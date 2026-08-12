# HubSpot Master Service

A Python FastAPI service that extracts data from HubSpot accounts on demand, processes and normalizes it into clean tables, and uploads the results to MinIO object storage.

## Overview

The HubSpot Master Service is designed to:
- Extract CRM data from HubSpot (contacts, companies, deals, tickets, owners)
- Handle OAuth authentication and automatic token refresh
- Implement cursor-based pagination with rate limiting
- Normalize raw HubSpot data into relational-style tables
- Upload normalized data as Parquet files to MinIO
- Support pause/resume/cancel operations
- Track job progress with checkpoints for crash recovery
- Provide HMAC-authenticated HTTP API for coordinator systems

**Important**: This service is NOT responsible for scheduling. A separate Coordinator system calls this service through HTTP APIs.

## Architecture

```
┌─────────────┐         ┌──────────────────┐
│ Coordinator │────────>│  FastAPI Service │
└─────────────┘  HMAC   └────────┬─────────┘
                                 │
                    ┌────────────┼────────────┐
                    │            │            │
                    v            v            v
              ┌──────────┐ ┌─────────┐ ┌──────────┐
              │ HubSpot  │ │   Job   │ │  MinIO   │
              │   API    │ │ Tracker │ │ Storage  │
              └──────────┘ │  (PG)   │ └──────────┘
                           └─────────┘
```

### Components

- **FastAPI Application**: HTTP API for job management
- **Extraction Service**: Manages data extraction jobs and pagination
- **Normalization Service**: Transforms raw HubSpot data into clean tables
- **HubSpot Clients**: OAuth authentication and CRM API access
- **PostgreSQL**: Job tracking, checkpoints, audit logs, dead letter queue
- **MinIO**: Object storage for normalized Parquet files

## Tech Stack

- **Python 3.11+**
- **FastAPI**: Web framework
- **PostgreSQL**: Job tracking and metadata
- **MinIO**: Object storage
- **Docker**: Containerization
- **HubSpot CRM API v3**: Data source
- **OAuth 2.0**: Authentication
- **HMAC-SHA256**: Request authentication

## Requirements

- Python 3.11 or higher
- PostgreSQL 15+
- MinIO or S3-compatible object storage
- HubSpot Developer Account with OAuth app configured
- Docker and Docker Compose (for containerized deployment)

## Quick Start

### 1. Clone Repository

```bash
git clone https://github.com/pbekana/hubspot-master-service.git
cd hubspot-master-service
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your actual credentials
```

Required environment variables:
- `HUBSPOT_CLIENT_ID`: Your HubSpot app client ID
- `HUBSPOT_CLIENT_SECRET`: Your HubSpot app client secret
- `DATABASE_URL`: PostgreSQL connection string
- `MINIO_ENDPOINT`: MinIO endpoint
- `MINIO_ACCESS_KEY`: MinIO access key
- `MINIO_SECRET_KEY`: MinIO secret key
- `HMAC_SECRET_KEY_CORE`: HMAC secret for coordinator
- `HMAC_SECRET_KEY_ENGINEER`: HMAC secret for read-only access

### 3. Run with Docker Compose

```bash
docker-compose up --build
```

This starts:
- FastAPI service on `http://localhost:3000`
- PostgreSQL on `localhost:5432`
- MinIO on `http://localhost:9000` (console: `http://localhost:9001`)

### 4. Access Services

- **API**: http://localhost:3000/docs (Swagger UI)
- **Health Check**: http://localhost:3000/api/health
- **MinIO Console**: http://localhost:9001 (minioadmin/minioadmin)

## Local Development Setup

### Install Dependencies

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Setup PostgreSQL

```bash
# Using Docker
docker run -d \
  --name hubspot-postgres \
  -e POSTGRES_USER=hubspot_user \
  -e POSTGRES_PASSWORD=hubspot_pass \
  -e POSTGRES_DB=hubspot_master \
  -p 5432:5432 \
  postgres:15-alpine
```

Or install PostgreSQL locally and create the database:

```sql
CREATE DATABASE hubspot_master;
CREATE USER hubspot_user WITH PASSWORD 'hubspot_pass';
GRANT ALL PRIVILEGES ON DATABASE hubspot_master TO hubspot_user;
```

### Setup MinIO

```bash
# Using Docker
docker run -d \
  --name hubspot-minio \
  -p 9000:9000 \
  -p 9001:9001 \
  -e MINIO_ROOT_USER=minioadmin \
  -e MINIO_ROOT_PASSWORD=minioadmin \
  minio/minio server /data --console-address ":9001"
```

### Run the Service

```bash
# Set environment variables
export DATABASE_URL=postgresql://hubspot_user:hubspot_pass@localhost:5432/hubspot_master
export HUBSPOT_CLIENT_ID=your_client_id
export HUBSPOT_CLIENT_SECRET=your_client_secret
# ... other variables

# Run with uvicorn
uvicorn apps.main:app --reload --port 3000
```

## HubSpot OAuth Setup

### 1. HubSpot Developer Project

The project already has a configured HubSpot Developer Project:
- **Project Name**: HubSpot Master Service
- **App Name**: HubSpot Master Service-App
- **Distribution**: Private
- **Authentication**: OAuth
- **Redirect URL**: http://localhost:3000

### 2. Required Scopes

- `oauth`
- `crm.objects.contacts.read`
- `crm.objects.companies.read`
- `crm.objects.deals.read`
- `tickets`

### 3. Get Access Token

#### Option A: Use existing test token (if available)

If you've already obtained an access token during testing, use it in your requests.

#### Option B: OAuth authorization flow

1. Build authorization URL:
```
https://app.hubspot.com/oauth/authorize?client_id=YOUR_CLIENT_ID&redirect_uri=http://localhost:3000&scope=oauth%20crm.objects.contacts.read%20crm.objects.companies.read%20crm.objects.deals.read%20tickets
```

2. User authorizes → receives authorization code

3. Exchange code for token:
```bash
POST https://api.hubapi.com/oauth/v1/token
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&
client_id=YOUR_CLIENT_ID&
client_secret=YOUR_CLIENT_SECRET&
redirect_uri=http://localhost:3000&
code=AUTHORIZATION_CODE
```

## API Documentation

### Authentication

All API endpoints (except `/api/health` and `/api/stats`) require HMAC authentication.

#### HMAC Headers

```
X-HS-Signature: <hmac-sha256-hex>
X-HS-Timestamp: <unix-timestamp>
X-HS-Client-ID: <client-id>
X-HS-Nonce: <random-nonce>
```

#### Computing Signature

Canonical string format:
```
METHOD\nPATH\nTIMESTAMP\nNONCE\nBODY_HASH
```

Example Python code:
```python
import hmac
import hashlib
import time
import json
import uuid

method = "POST"
path = "/api/scan/start"
timestamp = str(int(time.time()))
nonce = str(uuid.uuid4())
body = json.dumps({"organization_id": "org_123", ...})
body_hash = hashlib.sha256(body.encode()).hexdigest()

canonical = f"{method}\n{path}\n{timestamp}\n{nonce}\n{body_hash}"
signature = hmac.new(
    secret_key.encode(),
    canonical.encode(),
    hashlib.sha256
).hexdigest()
```

### Endpoints

#### Scan Management

**Start Scan**
```http
POST /api/scan/start
Content-Type: application/json

{
  "organization_id": "org_123",
  "object_types": ["contacts", "companies", "deals"],
  "access_token": "your_hubspot_access_token",
  "refresh_token": "your_refresh_token"
}

Response: 201 Created
{
  "id": 1,
  "organization_id": "org_123",
  "status": "RUNNING",
  "object_types": ["contacts", "companies", "deals"],
  "created_at": "2026-08-12T10:00:00Z"
}
```

**Get Scan Status**
```http
GET /api/scan/{scan_id}/status

Response: 200 OK
{
  "id": 1,
  "status": "RUNNING",
  "entity_record_counts": {
    "contacts": 150,
    "companies": 45
  },
  "last_heartbeat": "2026-08-12T10:05:00Z"
}
```

**Pause Scan**
```http
POST /api/scan/{scan_id}/pause

Response: 200 OK
{
  "id": 1,
  "status": "PAUSED"
}
```

**Resume Scan**
```http
POST /api/scan/{scan_id}/resume

Response: 200 OK
{
  "id": 1,
  "status": "RESUMING"
}
```

**Cancel Scan**
```http
POST /api/scan/{scan_id}/cancel

Response: 200 OK
{
  "id": 1,
  "status": "CANCELLED"
}
```

**List Scans**
```http
GET /api/scan/list?organization_id=org_123&status=COMPLETED&limit=10

Response: 200 OK
{
  "scans": [
    {
      "id": 1,
      "organization_id": "org_123",
      "status": "COMPLETED",
      "created_at": "2026-08-12T10:00:00Z"
    }
  ]
}
```

#### Normalization

**Normalize Scan**
```http
POST /api/normalization/{scan_id}/normalize
Content-Type: application/json

{
  "output_format": "parquet",
  "upload_to_minio": true
}

Response: 200 OK
{
  "scan_id": 1,
  "tables": ["contacts", "companies", "deals"],
  "status": "completed"
}
```

#### Maintenance

**Detect Crashed Jobs**
```http
POST /api/maintenance/detect-crashed
Content-Type: application/json

{
  "timeout_minutes": 30
}

Response: 200 OK
{
  "crashed_jobs": [1, 5, 9],
  "count": 3
}
```

## Job Lifecycle

```
PENDING → RUNNING → NORMALIZING → UPLOADING_TO_MINIO → COMPLETED
   │         │
   │         ├─> PAUSED → RESUMING → RUNNING
   │         │
   │         ├─> CANCELLED
   │         │
   │         └─> FAILED / CRASHED
```

### States

- **PENDING**: Job created, waiting to start
- **RUNNING**: Actively extracting data from HubSpot
- **PAUSED**: Paused by user, can be resumed
- **RESUMING**: Resuming from pause
- **NORMALIZING**: Transforming raw data into tables
- **UPLOADING_TO_MINIO**: Uploading normalized files
- **COMPLETED**: Successfully completed
- **FAILED**: Failed due to error
- **CANCELLED**: Cancelled by user
- **CRASHED**: Detected as crashed via stale heartbeat

## Pagination & Rate Limiting

### Cursor-Based Pagination

The service uses HubSpot's cursor-based pagination:
1. First request returns results + `paging.next.after` cursor
2. Next request includes cursor in `after` parameter
3. Continue until no `next` cursor is returned

### Rate Limit Handling

- **Burst limit**: 100 requests per 10 seconds (configurable)
- **429 handling**: Automatically waits for `Retry-After` header value
- **Fallback**: Uses default 5-second wait if `Retry-After` is missing
- **Separate from retries**: 429 is NOT counted as a failed retry

### Retry Logic

Retries for temporary failures:
- Connection errors
- Timeouts
- HTTP 500, 502, 503, 504

Retry strategy:
- Max retries: 3 (configurable)
- Delays: 1s, 2s, 4s (exponential backoff)
- Jitter: ±50% randomization
- Exhausted retries → Dead Letter Queue

## Checkpointing & Resume

### How Checkpoints Work

After each successful page:
1. Save cursor value
2. Update records processed count
3. Update timestamp

### Crash Recovery

If a job crashes (detected via stale heartbeat):
1. Job status → `CRASHED`
2. Resume from last checkpoint
3. Continue from saved cursor position

### Pause & Resume

**Pause**: Cooperative check between pages
- Does NOT interrupt active HTTP requests
- Waits for current page to complete
- Saves checkpoint before pausing

**Resume**: Continues from last checkpoint
- Loads cursor and record count
- Resumes pagination
- No data duplication

## Normalization

### Supported Object Types

- **Contacts** → `contacts` table
- **Companies** → `companies` table
- **Deals** → `deals`, `deal_line_items`, `deal_associations` tables
- **Tickets** → `tickets` table
- **Owners** → `owners` table

### Output Format

- **Primary**: Parquet files
- **Development**: JSON (optional)

### MinIO Structure

```
hubspot/
  ├── contacts/
  │   └── glynac_organization_id=org_123/
  │       └── processing_date=2026-08-12/
  │           └── contacts.parquet
  ├── companies/
  │   └── glynac_organization_id=org_123/
  │       └── processing_date=2026-08-12/
  │           └── companies.parquet
  └── deals/
      └── glynac_organization_id=org_123/
          └── processing_date=2026-08-12/
              └── deals.parquet
```

## Testing

### Run Tests

```bash
# All tests
pytest

# With coverage
pytest --cov=apps --cov-report=html

# Specific test file
pytest tests/test_pagination.py -v

# Specific test
pytest tests/test_pagination.py::test_get_first_page -v
```

### Test Categories

- **Authentication**: OAuth token exchange and refresh
- **Pagination**: Multi-page fetching with cursors
- **Rate Limiting**: 429 handling and Retry-After
- **Retry Logic**: Temporary failure handling
- **Job Lifecycle**: Create, pause, resume, cancel
- **Checkpoints**: Save, load, resume from cursor
- **Normalization**: Data transformation
- **Security**: HMAC authentication and authorization
- **MinIO**: File upload and error handling

## Known Limitations

1. **No scheduling**: Requires external coordinator
2. **No deduplication**: Assumes clean extraction per run
3. **No PII masking**: Raw data is stored as-is
4. **Token encryption**: Basic implementation (enhance for production)
5. **Nonce replay protection**: Not fully implemented
6. **Concurrent jobs**: Single-threaded extraction per job

## Security

### Secrets Management

- **Never commit**: `.env`, tokens, secrets, passwords
- **Use environment variables**: All sensitive config
- **Encryption**: Access/refresh tokens should be encrypted in database
- **HMAC**: Required for all coordinator endpoints
- **Audit logging**: All operations are logged

### HMAC Client Roles

- **Coordinator** (`hmac_secret_key_core`): Full access (read + write)
- **Engineer** (`hmac_secret_key_engineer`): Read-only access

## Troubleshooting

### Common Issues

**Database connection failed**
```bash
# Check PostgreSQL is running
docker ps | grep postgres

# Test connection
psql postgresql://hubspot_user:hubspot_pass@localhost:5432/hubspot_master
```

**MinIO connection failed**
```bash
# Check MinIO is running
docker ps | grep minio

# Test connection
curl http://localhost:9000/minio/health/live
```

**OAuth token expired**
- The service automatically refreshes tokens using the refresh token
- If refresh fails, you'll need to re-authorize the app

**Job stuck in RUNNING**
- Use detect-crashed endpoint to find stale jobs
- Check heartbeat timestamp
- Resume crashed jobs from checkpoints

## Contributing

1. Follow existing code structure
2. Write tests for new features
3. Update documentation
4. Never commit secrets
5. Use meaningful commit messages

## License

[Your License Here]

## Support

For issues and questions, see DESIGN.md for architecture details or open an issue on GitHub.
