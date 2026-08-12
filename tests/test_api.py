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
    fake_job = type("JobObj", (), {"to_dict": lambda self: {"id": 1, "status": "PENDING", "organization_id": "org1", "object_types": ["contacts"]}})()
    monkeypatch.setattr("apps.api.scan.ExtractionService.start_scan", lambda self, **kwargs: fake_job)

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
    monkeypatch.setattr("apps.services.extraction_service.asyncio.create_task", lambda coro: None)

    running_job = Job(
        organization_id="org3",
        status=JobStatus.RUNNING,
        object_types=["contacts"],
        access_token_encrypted="token",
        refresh_token_encrypted="refresh",
        last_heartbeat=datetime.utcnow(),
    )
    paused_job = Job(
        organization_id="org3",
        status=JobStatus.PAUSED,
        object_types=["contacts"],
        access_token_encrypted="token",
        refresh_token_encrypted="refresh",
        last_heartbeat=datetime.utcnow(),
    )
    pending_job = Job(
        organization_id="org3",
        status=JobStatus.PENDING,
        object_types=["contacts"],
        access_token_encrypted="token",
        refresh_token_encrypted="refresh",
        last_heartbeat=datetime.utcnow(),
    )
    db_session.add_all([running_job, paused_job, pending_job])
    db_session.commit()

    headers = hmac_headers("POST", f"/api/scan/{running_job.id}/pause", b"", client_id="coordinator")
    response = client.post(f"/api/scan/{running_job.id}/pause", headers=headers)
    assert response.status_code == 200

    headers = hmac_headers("POST", f"/api/scan/{paused_job.id}/resume", b"", client_id="coordinator")
    response = client.post(f"/api/scan/{paused_job.id}/resume", headers=headers)
    assert response.status_code == 200

    headers = hmac_headers("POST", f"/api/scan/{pending_job.id}/cancel", b"", client_id="coordinator")
    response = client.post(f"/api/scan/{pending_job.id}/cancel", headers=headers)
    assert response.status_code == 200

    checkpoint = Checkpoint(
        job_id=pending_job.id,
        object_type="contacts",
        cursor="abc",
        records_processed=1,
    )
    db_session.add(checkpoint)
    db_session.commit()

    headers = hmac_headers("DELETE", f"/api/scan/{pending_job.id}/remove", b"", client_id="coordinator")
    response = client.delete(f"/api/scan/{pending_job.id}/remove", headers=headers)
    assert response.status_code == 204
    assert db_session.get(Job, pending_job.id) is None


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
    monkeypatch.setattr("apps.api.credentials.HubSpotAuthClient.validate_credentials", lambda self, access_token, refresh_token=None: True)

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


def test_audit_logs_and_stats_endpoints(client, hmac_headers, db_session):
    audit_service = AuditService(db_session)
    audit_service.log_event(
        event_category=AuditEventCategory.API_REQUEST,
        event_type="GET",
        outcome=AuditOutcome.SUCCESS,
        severity=AuditSeverity.INFO,
        organization_id="org6",
    )

    payload = {"organization_id": "org6", "limit": 10}
    body = json.dumps(payload).encode("utf-8")
    headers = hmac_headers("POST", "/api/audit/logs", body, client_id="engineer")
    headers["Content-Type"] = "application/json"

    response = client.post("/api/audit/logs", data=body, headers=headers)
    assert response.status_code == 200
    assert response.json()["total"] == 1

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
