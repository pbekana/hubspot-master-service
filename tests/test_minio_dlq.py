import pytest
from unittest.mock import MagicMock
from minio.error import S3Error
from apps.clients.minio_client import MinIOClient
from apps.utils.dlq import write_to_dlq
from apps.models.job import Job
from apps.models.failed_external_call import FailedExternalCall
from apps.models.job import JobStatus
from datetime import datetime


def test_ensure_bucket_exists_creates_bucket_when_missing():
    client = MinIOClient()
    client.client = MagicMock()
    client.client.bucket_exists.return_value = False

    client.ensure_bucket_exists()

    client.client.bucket_exists.assert_called_once_with(client.bucket)
    client.client.make_bucket.assert_called_once_with(client.bucket)


@pytest.mark.asyncio
async def test_upload_file_success(tmp_path):
    test_file = tmp_path / "upload_test.txt"
    test_file.write_text("hello")

    client = MinIOClient()
    client.client = MagicMock()
    client.client.bucket_exists.return_value = True
    client.client.fput_object.return_value = None

    result = await client.upload_file(str(test_file), "path/to/test.txt")

    assert result == "path/to/test.txt"
    client.client.fput_object.assert_called_once()


@pytest.mark.asyncio
async def test_upload_normalized_data_generates_expected_object_keys():
    client = MinIOClient()
    # Mock upload_file to return the object key synchronously
    async def mock_upload(local_path, object_key, content_type="application/octet-stream"):
        return object_key
    client.upload_file = mock_upload

    result = await client.upload_normalized_data(
        scan_id=1,
        organization_id="org1",
        processing_date=datetime(2026, 8, 12),
        tables={"contacts": "local_contacts.parquet"},
    )

    assert "contacts" in result
    assert result["contacts"].startswith("hubspot/contacts/")
    assert result["contacts"].endswith("contacts.parquet")


@pytest.mark.asyncio
async def test_upload_file_failure_raises(tmp_path):
    test_file = tmp_path / "failure.txt"
    test_file.write_text("error")

    client = MinIOClient()
    client.client = MagicMock()
    client.client.bucket_exists.return_value = True
    # S3Error requires specific parameters
    client.client.fput_object.side_effect = Exception("Upload failed")

    with pytest.raises(Exception):
        await client.upload_file(str(test_file), "path/to/failure.txt")


def test_write_to_dlq_scrubs_sensitive_fields(db_session):
    payload = {
        "access_token": "secret-token",
        "client_secret": "secret",
        "email": "user@example.com",
    }
    error = Exception("failure")

    record = write_to_dlq(
        db=db_session,
        target_service="hubspot",
        operation="test_operation",
        payload=payload,
        attempts=2,
        error=error,
        organization_id="org1",
        scan_id=123,
    )

    assert record is not None
    assert record.payload is not None
    assert "[REDACTED]" in record.payload
    assert "secret-token" not in record.payload
    assert record.attempts == 2
    assert record.organization_id == "org1"
    assert record.scan_id == 123
