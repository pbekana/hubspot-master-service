import json
from datetime import datetime, timedelta
import pytest
from apps.models.job import Job, JobStatus
from apps.models.checkpoint import Checkpoint
from apps.models.audit import AuditEventCategory, AuditOutcome, AuditSeverity
from apps.services.audit_service import AuditService


def test_health_endpoint(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_stats_endpoint(client):
    response = client.get("/api/stats")
    assert response.status_code == 200
    assert response.json()["service"] == "hubspot-master-service"


def test_start_scan_endpoint_requires_coordinator(client, hmac_headers, monkeypatch):
    class FakeJob:
        def __init__(self):
            self.id = 1
            self.status = "PENDING"
            self.organization_id = "org1"
            self.object_types = ["contacts"]
        
        def to_dict(self):
            return {
                "id": self.id,
                "status": self.status,
                "organization_id": self.organization_id,
                "object_types": self.object_types,
                "entity_record_counts": {},
                "created_at": None,
                "updated_at": None,
                "normalized_at": None,
                "minio_uploaded_at": None,
                "last_heartbeat": None,
                "error_message": None,
            }
    
    monkeypatch.setattr("apps.api.scan.ExtractionService.start_scan", lambda self, **kwargs: FakeJob())

    payload = {
        "organization_id": "org1",
        "object_types": ["contacts"],
        "access_token": "token",
        "refresh_token": "refresh",
    }
    body = json.dumps(payload).encode("utf-8")
    headers = hmac_headers("POST", "/api/scan/start", body, client_id="coordinator")
    headers["Content-Type"] = "application/json"

    response = client.post("/api/scan/start", data=body, headers=headers)
    assert response.status_code == 201
    assert response.json()["organization_id"] == "org1"


def test_scan_status_endpoint_with_engineer_auth(client, hmac_headers, db_session):
    job = Job(
        organization_id="org2",
        status=JobStatus.PENDING,
        object_types=["contacts"],
        access_token_encrypted="token",
        refresh_token_encrypted="refresh",
        last_heartbeat=datetime.utcnow(),
    )
    db_session.add(job)
    db_session.commit()

    headers = hmac_headers("GET", f"/api/scan/{job.id}/status", b"", client_id="engineer")
    response = client.get(f"/api/scan/{job.id}/status", headers=headers)

    assert response.status_code == 200
    assert response.json()["id"] == job.id


def test_pause_resume_cancel_and_remove_endpoints(client, hmac_headers, db_session, monkeypatch):
    # Mock the extraction service to avoid actual database operations
    monkeypatch.setattr("apps.services.extraction_service.asyncio.create_task", lambda coro: None)
    
    # Mock the extraction service methods to avoid database conflicts
    def mock_pause_scan(self, job_id):
        # Create a mock job object with the required attributes
        class MockJob:
            def __init__(self, job_id):
                self.id = job_id
                self.status = "PAUSED"
                self.organization_id = "org3"
                self.object_types = ["contacts"]
                
            def to_dict(self):
                return {
                    "id": self.id,
                    "status": self.status,
                    "organization_id": self.organization_id,
                    "object_types": self.object_types,
                    "entity_record_counts": {},
                    "created_at": None,
                    "updated_at": None,
                    "normalized_at": None,
                    "minio_uploaded_at": None,
                    "last_heartbeat": None,
                    "error_message": None,
                }
        return MockJob(job_id)
    
    def mock_resume_scan(self, job_id):
        class MockJob:
            def __init__(self, job_id):
                self.id = job_id
                self.status = "RESUMING"
                self.organization_id = "org3"
                self.object_types = ["contacts"]
                
            def to_dict(self):
                return {
                    "id": self.id,
                    "status": self.status,
                    "organization_id": self.organization_id,
                    "object_types": self.object_types,
                    "entity_record_counts": {},
                    "created_at": None,
                    "updated_at": None,
                    "normalized_at": None,
                    "minio_uploaded_at": None,
                    "last_heartbeat": None,
                    "error_message": None,
                }
        return MockJob(job_id)
    
    def mock_cancel_scan(self, job_id):
        class MockJob:
            def __init__(self, job_id):
                self.id = job_id
                self.status = "CANCELLED"
                self.organization_id = "org3"
                self.object_types = ["contacts"]
                
            def to_dict(self):
                return {
                    "id": self.id,
                    "status": self.status,
                    "organization_id": self.organization_id,
                    "object_types": self.object_types,
                    "entity_record_counts": {},
                    "created_at": None,
                    "updated_at": None,
                    "normalized_at": None,
                    "minio_uploaded_at": None,
                    "last_heartbeat": None,
                    "error_message": None,
                }
        return MockJob(job_id)
    
    def mock_remove_scan(self, job_id):
        return None  # Remove operation doesn't return a job
    
    monkeypatch.setattr("apps.api.scan.ExtractionService.pause_scan", mock_pause_scan)
    monkeypatch.setattr("apps.api.scan.ExtractionService.resume_scan", mock_resume_scan)
    monkeypatch.setattr("apps.api.scan.ExtractionService.cancel_scan", mock_cancel_scan) 
    monkeypatch.setattr("apps.api.scan.ExtractionService.remove_scan", mock_remove_scan)

    # Test pause endpoint
    headers = hmac_headers("POST", "/api/scan/1/pause", b"", client_id="coordinator")
    response = client.post("/api/scan/1/pause", headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "PAUSED"

    # Test resume endpoint  
    headers = hmac_headers("POST", "/api/scan/2/resume", b"", client_id="coordinator")
    response = client.post("/api/scan/2/resume", headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "RESUMING"

    # Test cancel endpoint
    headers = hmac_headers("POST", "/api/scan/3/cancel", b"", client_id="coordinator")
    response = client.post("/api/scan/3/cancel", headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"

    # Test remove endpoint
    headers = hmac_headers("DELETE", "/api/scan/4/remove", b"", client_id="coordinator")
    response = client.delete("/api/scan/4/remove", headers=headers)
    assert response.status_code == 204


def test_scan_list_and_statistics_endpoints(client, hmac_headers, db_session):
    jobs = [
        Job(
            organization_id="org4",
            status=JobStatus.COMPLETED,
            object_types=["owners"],
            access_token_encrypted="token",
            refresh_token_encrypted="refresh",
            last_heartbeat=datetime.utcnow(),
        ),
        Job(
            organization_id="org4",
            status=JobStatus.FAILED,
            object_types=["owners"],
            access_token_encrypted="token",
            refresh_token_encrypted="refresh",
            last_heartbeat=datetime.utcnow(),
        ),
    ]
    db_session.add_all(jobs)
    db_session.commit()

    headers = hmac_headers("GET", "/api/scan/list", b"", client_id="engineer")
    response = client.get("/api/scan/list", headers=headers)
    assert response.status_code == 200
    assert response.json()["total"] >= 2

    headers = hmac_headers("GET", "/api/scan/statistics", b"", client_id="engineer")
    response = client.get("/api/scan/statistics", headers=headers)
    assert response.status_code == 200
    assert "completed" in response.json()


def test_validate_credentials_endpoint(client, hmac_headers, monkeypatch):
    async def mock_validate(self, access_token, refresh_token=None):
        return True
    
    monkeypatch.setattr("apps.api.credentials.HubSpotAuthClient.validate_credentials", mock_validate)

    payload = {"access_token": "token"}
    body = json.dumps(payload).encode("utf-8")
    headers = hmac_headers("POST", "/api/validate-credentials", body, client_id="engineer")
    headers["Content-Type"] = "application/json"

    response = client.post("/api/validate-credentials", data=body, headers=headers)
    assert response.status_code == 200
    assert response.json()["valid"] is True


def test_maintenance_endpoints(client, hmac_headers, db_session):
    old_job = Job(
        organization_id="org5",
        status=JobStatus.COMPLETED,
        object_types=["deals"],
        access_token_encrypted="token",
        refresh_token_encrypted="refresh",
        last_heartbeat=datetime.utcnow() - timedelta(days=31),
        updated_at=datetime.utcnow() - timedelta(days=31),
    )
    db_session.add(old_job)
    db_session.commit()

    payload = {"days_old": 0}
    body = json.dumps(payload).encode("utf-8")
    headers = hmac_headers("POST", "/api/maintenance/cleanup", body, client_id="coordinator")
    headers["Content-Type"] = "application/json"

    response = client.post("/api/maintenance/cleanup", data=body, headers=headers)
    assert response.status_code == 200
    assert response.json()["deleted_jobs"] >= 1

    stale_job = Job(
        organization_id="org5",
        status=JobStatus.RUNNING,
        object_types=["deals"],
        access_token_encrypted="token",
        refresh_token_encrypted="refresh",
        last_heartbeat=datetime.utcnow() - timedelta(minutes=61),
    )
    db_session.add(stale_job)
    db_session.commit()

    payload = {"timeout_minutes": 30}
    body = json.dumps(payload).encode("utf-8")
    headers = hmac_headers("POST", "/api/maintenance/detect-crashed", body, client_id="coordinator")
    headers["Content-Type"] = "application/json"

    response = client.post("/api/maintenance/detect-crashed", data=body, headers=headers)
    assert response.status_code == 200
    assert response.json()["count"] >= 1


def test_audit_logs_and_stats_endpoints(client, hmac_headers, db_session, monkeypatch):
    # Mock audit service methods to avoid session isolation issues
    def mock_get_logs(self, organization_id=None, event_category=None, start_date=None, end_date=None, limit=100):
        # Create a mock audit log object
        class MockAuditLog:
            def __init__(self):
                from apps.models.audit import AuditEventCategory, AuditOutcome, AuditSeverity
                from datetime import datetime
                self.id = 1
                self.event_category = AuditEventCategory.API_REQUEST
                self.event_type = "GET"
                self.actor_client_id = "engineer"
                self.organization_id = "org6"
                self.outcome = AuditOutcome.SUCCESS
                self.severity = AuditSeverity.INFO
                self.created_at = datetime.utcnow()
        
        return [MockAuditLog()]
    
    def mock_get_statistics(self):
        return {
            "total_events": 1,
            "by_category": {"API_REQUEST": 1},
            "by_outcome": {"SUCCESS": 1},
            "by_severity": {"INFO": 1}
        }
    
    monkeypatch.setattr("apps.api.audit.AuditService.get_logs", mock_get_logs)
    monkeypatch.setattr("apps.api.audit.AuditService.get_statistics", mock_get_statistics)

    payload = {"organization_id": "org6", "limit": 10}
    body = json.dumps(payload).encode("utf-8")
    headers = hmac_headers("POST", "/api/audit/logs", body, client_id="engineer")
    headers["Content-Type"] = "application/json"

    response = client.post("/api/audit/logs", data=body, headers=headers)
    assert response.status_code == 200
    assert response.json()["total"] >= 1

    headers = hmac_headers("GET", "/api/audit/stats", b"", client_id="engineer")
    response = client.get("/api/audit/stats", headers=headers)
    assert response.status_code == 200
    assert response.json()["total_events"] >= 1


def test_engineer_cannot_start_scan(client, hmac_headers):
    payload = {
        "organization_id": "org1",
        "object_types": ["contacts"],
        "access_token": "token",
    }
    body = json.dumps(payload).encode("utf-8")
    headers = hmac_headers("POST", "/api/scan/start", body, client_id="engineer")
    headers["Content-Type"] = "application/json"

    response = client.post("/api/scan/start", data=body, headers=headers)
    assert response.status_code == 403
