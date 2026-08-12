import os
import shutil
from pathlib import Path
import pytest
import pandas as pd
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime
from apps.services.normalization_service import NormalizationService
from apps.models.job import Job, JobStatus
from apps.services.normalizers.contact_normalizer import ContactNormalizer
from apps.services.normalizers.company_normalizer import CompanyNormalizer
from apps.services.normalizers.deal_normalizer import DealNormalizer
from apps.services.normalizers.ticket_normalizer import TicketNormalizer
from apps.services.normalizers.owner_normalizer import OwnerNormalizer


def test_contact_normalizer_normalizes_records():
    normalizer = ContactNormalizer()
    raw = [
        {
            "id": "c1",
            "properties": {
                "email": "test@example.com",
                "firstname": "Jane",
                "lastname": "Doe",
            },
            "createdAt": "2026-08-01T00:00:00Z",
            "updatedAt": "2026-08-02T00:00:00Z",
            "archived": False,
        }
    ]

    df = normalizer.normalize(raw)

    assert df.iloc[0]["email"] == "test@example.com"
    assert df.iloc[0]["firstname"] == "Jane"
    assert "_extracted_at" in df.columns


def test_company_normalizer_handles_missing_values():
    normalizer = CompanyNormalizer()
    raw = [
        {
            "id": "co1",
            "properties": {
                "name": None,
                "domain": "example.com",
            },
            "createdAt": None,
            "updatedAt": None,
            "archived": True,
        }
    ]

    df = normalizer.normalize(raw)

    assert df.iloc[0]["name"] is None
    assert df.iloc[0]["domain"] == "example.com"
    assert df.iloc[0]["archived"] is True


def test_deal_normalizer_generates_line_items_and_associations():
    normalizer = DealNormalizer()
    raw = [
        {
            "id": "d1",
            "properties": {
                "dealname": "Deal 1",
                "amount": "1000",
            },
            "line_items": [
                {
                    "name": "Line Item 1",
                    "quantity": 2,
                    "price": 500,
                    "amount": 1000,
                    "hs_product_id": "prod_1",
                    "hs_sku": "sku_1",
                }
            ],
            "associations": {
                "contacts": [
                    {"id": "c1", "type": "contact"}
                ]
            },
            "createdAt": "2026-08-01T00:00:00Z",
            "updatedAt": "2026-08-02T00:00:00Z",
            "archived": False,
        }
    ]

    result = normalizer.normalize(raw)

    assert "deals" in result
    assert "deal_line_items" in result
    assert "deal_associations" in result
    assert result["deal_line_items"].iloc[0]["deal_id"] == "d1"
    assert result["deal_associations"].iloc[0]["associated_id"] == "c1"


def test_ticket_normalizer_handles_multiple_records():
    normalizer = TicketNormalizer()
    raw = [
        {
            "id": "t1",
            "properties": {"subject": "Help", "hs_ticket_priority": "HIGH"},
            "createdAt": "2026-08-01T00:00:00Z",
            "updatedAt": "2026-08-02T00:00:00Z",
            "archived": False,
        },
        {
            "id": "t2",
            "properties": {"subject": "Support", "hs_ticket_priority": None},
            "createdAt": "2026-08-01T01:00:00Z",
            "updatedAt": "2026-08-02T01:00:00Z",
            "archived": False,
        },
    ]

    df = normalizer.normalize(raw)

    assert len(df) == 2
    assert df.iloc[1]["subject"] == "Support"


def test_owner_normalizer_handles_root_and_property_fields():
    normalizer = OwnerNormalizer()
    raw = [
        {
            "id": "o1",
            "ownerId": "owner_1",
            "email": "owner@example.com",
            "firstName": "Owner",
            "properties": {"hs_object_id": "1"},
            "createdAt": "2026-08-01T00:00:00Z",
            "updatedAt": "2026-08-02T00:00:00Z",
        }
    ]

    df = normalizer.normalize(raw)

    assert df.iloc[0]["ownerId"] == "owner_1"
    assert df.iloc[0]["email"] == "owner@example.com"


def test_save_table_writes_parquet_file(db_session):
    service = NormalizationService(db_session)
    df = pd.DataFrame([{"id": "1", "email": "test@example.com"}])

    file_path = service._save_table(scan_id=99, table_name="contacts", df=df, output_format="parquet")
    output_path = Path(file_path)

    assert output_path.exists()
    loaded = pd.read_parquet(str(output_path), engine="pyarrow")
    assert "email" in loaded.columns
    assert loaded.iloc[0]["email"] == "test@example.com"

    shutil.rmtree(service.data_dir / f"scan_99", ignore_errors=True)


@pytest.mark.asyncio
async def test_normalize_scan_empty_dataset_does_not_fail(db_session):
    service = NormalizationService(db_session)
    job = Job(
        organization_id="org8",
        status=JobStatus.COMPLETED,
        object_types=["contacts"],
        access_token_encrypted="token",
        refresh_token_encrypted="refresh",
        last_heartbeat=datetime.utcnow(),
    )
    db_session.add(job)
    db_session.commit()

    service._load_raw_data = lambda scan_id, object_types: {"contacts": []}
    service.minio_client = MagicMock()

    result = await service.normalize_scan(scan_id=job.id, upload_to_minio=False)

    assert result["tables"] == []
    assert result["minio_objects"] is None


@pytest.mark.asyncio
async def test_normalize_scan_creates_multiple_tables_and_uploads(db_session):
    service = NormalizationService(db_session)
    job = Job(
        organization_id="org9",
        status=JobStatus.COMPLETED,
        object_types=["deals"],
        access_token_encrypted="token",
        refresh_token_encrypted="refresh",
        last_heartbeat=datetime.utcnow(),
    )
    db_session.add(job)
    db_session.commit()

    service._load_raw_data = lambda scan_id, object_types: {
        "deals": [
            {
                "id": "d1",
                "properties": {"dealname": "Deal 1"},
                "line_items": [
                    {"name": "Item 1", "quantity": 1, "price": 100, "amount": 100, "hs_product_id": "p1"}
                ],
                "associations": {"contacts": [{"id": "c1", "type": "contact"}]},
                "createdAt": "2026-08-01T00:00:00Z",
                "updatedAt": "2026-08-02T00:00:00Z",
                "archived": False,
            }
        ]
    }
    service.minio_client = MagicMock()
    service.minio_client.upload_normalized_data = AsyncMock(
        return_value={
            "deals": "hubspot/deals/.../deals.parquet",
            "deal_line_items": "hubspot/deal_line_items/.../deal_line_items.parquet",
            "deal_associations": "hubspot/deal_associations/.../deal_associations.parquet",
        }
    )

    result = await service.normalize_scan(scan_id=job.id, upload_to_minio=True)

    assert sorted(result["tables"]) == ["deal_associations", "deal_line_items", "deals"]
    assert result["minio_objects"]["deals"].endswith("deals.parquet")

    scan_dir = service.data_dir / f"scan_{job.id}"
    assert (scan_dir / "deals.parquet").exists()
    assert (scan_dir / "deal_line_items.parquet").exists()
    assert (scan_dir / "deal_associations.parquet").exists()

    shutil.rmtree(scan_dir, ignore_errors=True)
