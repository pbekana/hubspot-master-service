import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, AsyncMock
from apps.services.extraction_service import ExtractionService
from apps.models.job import Job, JobStatus
from apps.models.checkpoint import Checkpoint


@pytest.mark.asyncio
async def test_start_scan_creates_pending_job(db_session):
    with patch("apps.services.extraction_service.asyncio.create_task") as create_task:
        service = ExtractionService(db_session)
        job = service.start_scan(
            organization_id="org1",
            object_types=["contacts"],
            access_token="token",
            refresh_token="refresh",
        )

        assert job.id is not None
        assert job.status == JobStatus.PENDING
        assert job.organization_id == "org1"
        assert create_task.called


def test_pause_scan_valid_and_invalid(db_session):
    service = ExtractionService(db_session)

    running_job = Job(
        organization_id="org2",
        status=JobStatus.RUNNING,
        object_types=["contacts"],
        access_token_encrypted="token",
        refresh_token_encrypted="refresh",
        last_heartbeat=datetime.utcnow(),
    )
    db_session.add(running_job)
    db_session.commit()

    result = service.pause_scan(running_job.id)
    assert result.status == JobStatus.RUNNING
    assert service._pause_flags[running_job.id] is True

    pending_job = Job(
        organization_id="org2",
        status=JobStatus.PENDING,
        object_types=["contacts"],
        access_token_encrypted="token",
        refresh_token_encrypted="refresh",
        last_heartbeat=datetime.utcnow(),
    )
    db_session.add(pending_job)
    db_session.commit()

    with pytest.raises(ValueError, match="is not running"):
        service.pause_scan(pending_job.id)


@pytest.mark.asyncio
async def test_resume_scan_valid_and_invalid(db_session):
    service = ExtractionService(db_session)

    paused_job = Job(
        organization_id="org3",
        status=JobStatus.PAUSED,
        object_types=["companies"],
        access_token_encrypted="token",
        refresh_token_encrypted="refresh",
        last_heartbeat=datetime.utcnow(),
    )
    db_session.add(paused_job)
    db_session.commit()

    with patch("apps.services.extraction_service.asyncio.create_task") as create_task:
        result = service.resume_scan(paused_job.id)

        assert result.status == JobStatus.RESUMING
        assert service._pause_flags.get(paused_job.id, False) is False
        assert create_task.called

    running_job = Job(
        organization_id="org3",
        status=JobStatus.RUNNING,
        object_types=["companies"],
        access_token_encrypted="token",
        refresh_token_encrypted="refresh",
        last_heartbeat=datetime.utcnow(),
    )
    db_session.add(running_job)
    db_session.commit()

    with pytest.raises(ValueError, match="is not paused"):
        service.resume_scan(running_job.id)


def test_cancel_scan_valid_and_invalid(db_session):
    service = ExtractionService(db_session)

    pending_job = Job(
        organization_id="org4",
        status=JobStatus.PENDING,
        object_types=["deals"],
        access_token_encrypted="token",
        refresh_token_encrypted="refresh",
        last_heartbeat=datetime.utcnow(),
    )
    db_session.add(pending_job)
    db_session.commit()

    result = service.cancel_scan(pending_job.id)
    assert service._cancel_flags[pending_job.id] is True
    assert result.status == JobStatus.PENDING

    completed_job = Job(
        organization_id="org4",
        status=JobStatus.COMPLETED,
        object_types=["deals"],
        access_token_encrypted="token",
        refresh_token_encrypted="refresh",
        last_heartbeat=datetime.utcnow(),
    )
    db_session.add(completed_job)
    db_session.commit()

    with pytest.raises(ValueError, match="terminal state"):
        service.cancel_scan(completed_job.id)


def test_detect_crashed_jobs(db_session):
    service = ExtractionService(db_session)

    stale_job = Job(
        organization_id="org5",
        status=JobStatus.RUNNING,
        object_types=["tickets"],
        access_token_encrypted="token",
        refresh_token_encrypted="refresh",
        last_heartbeat=datetime.utcnow() - timedelta(minutes=61),
    )
    db_session.add(stale_job)
    db_session.commit()

    crashed_jobs = service.detect_crashed_jobs(timeout_minutes=30)

    assert len(crashed_jobs) == 1
    assert crashed_jobs[0].status == JobStatus.CRASHED


def test_remove_scan_deletes_job_and_checkpoint(db_session):
    service = ExtractionService(db_session)

    job = Job(
        organization_id="org6",
        status=JobStatus.PENDING,
        object_types=["owners"],
        access_token_encrypted="token",
        refresh_token_encrypted="refresh",
        last_heartbeat=datetime.utcnow(),
    )
    db_session.add(job)
    db_session.commit()

    checkpoint = Checkpoint(
        job_id=job.id,
        object_type="owners",
        cursor="cursor123",
        records_processed=5,
    )
    db_session.add(checkpoint)
    db_session.commit()

    service.remove_scan(job.id)

    assert db_session.get(Job, job.id) is None
    assert db_session.query(Checkpoint).filter_by(job_id=job.id).count() == 0


@pytest.mark.asyncio
async def test_checkpoint_persistence_resumes_from_cursor(db_session):
    service = ExtractionService(db_session)

    job = Job(
        organization_id="org7",
        status=JobStatus.RUNNING,
        object_types=["contacts"],
        access_token_encrypted="token",
        refresh_token_encrypted="refresh",
        last_heartbeat=datetime.utcnow(),
    )
    db_session.add(job)
    db_session.commit()

    checkpoint = Checkpoint(
        job_id=job.id,
        object_type="contacts",
        cursor="cursor_abc",
        records_processed=5,
    )
    db_session.add(checkpoint)
    db_session.commit()

    api_client = AsyncMock()
    api_client.get_page.return_value = {
        "results": [{"id": "6", "properties": {"email": "test6@example.com"}}],
        "paging": {},
    }

    total = await service._extract_object_type(
        job_id=job.id,
        object_type="contacts",
        api_client=api_client,
        checkpoint=checkpoint,
    )

    api_client.get_page.assert_awaited_once_with(object_type="contacts", after_cursor="cursor_abc")
    assert total == 6
    assert checkpoint.cursor is None
    assert checkpoint.records_processed == 6
