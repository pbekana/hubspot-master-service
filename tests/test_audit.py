import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock
from apps.services.audit_service import AuditService
from apps.models.audit import AuditEventCategory, AuditOutcome, AuditSeverity


def test_log_event_success(db_session):
    service = AuditService(db_session)

    log = service.log_event(
        event_category=AuditEventCategory.AUTHENTICATION,
        event_type="login",
        outcome=AuditOutcome.SUCCESS,
        severity=AuditSeverity.INFO,
        actor_client_id="coordinator",
        organization_id="org1",
        status_code=200,
    )

    assert log is not None
    assert log.event_category == AuditEventCategory.AUTHENTICATION
    assert log.outcome == AuditOutcome.SUCCESS
    assert log.actor_client_id == "coordinator"


def test_get_logs_filters(db_session):
    service = AuditService(db_session)

    service.log_event(
        event_category=AuditEventCategory.SYSTEM,
        event_type="start",
        outcome=AuditOutcome.SUCCESS,
        severity=AuditSeverity.INFO,
        organization_id="org1",
    )
    service.log_event(
        event_category=AuditEventCategory.SYSTEM,
        event_type="stop",
        outcome=AuditOutcome.FAILURE,
        severity=AuditSeverity.ERROR,
        organization_id="org2",
    )

    logs = service.get_logs(organization_id="org1", limit=10)
    assert len(logs) == 1
    assert logs[0].organization_id == "org1"


def test_get_statistics_counts_categories_and_outcomes(db_session):
    service = AuditService(db_session)

    service.log_event(
        event_category=AuditEventCategory.DATA_EXTRACTION,
        event_type="extract",
        outcome=AuditOutcome.SUCCESS,
        severity=AuditSeverity.INFO,
    )
    service.log_event(
        event_category=AuditEventCategory.DATA_EXTRACTION,
        event_type="extract",
        outcome=AuditOutcome.FAILURE,
        severity=AuditSeverity.ERROR,
    )

    stats = service.get_statistics()

    assert stats["total_events"] == 2
    assert stats["by_category"][AuditEventCategory.DATA_EXTRACTION.value] == 2
    assert stats["by_outcome"][AuditOutcome.SUCCESS.value] == 1
    assert stats["by_outcome"][AuditOutcome.FAILURE.value] == 1


def test_cleanup_old_logs(db_session):
    service = AuditService(db_session)

    old_log = service.log_event(
        event_category=AuditEventCategory.SYSTEM,
        event_type="old",
        outcome=AuditOutcome.SUCCESS,
        severity=AuditSeverity.INFO,
    )
    old_log.created_at = datetime.utcnow() - timedelta(days=31)
    db_session.commit()

    service.log_event(
        event_category=AuditEventCategory.SYSTEM,
        event_type="new",
        outcome=AuditOutcome.SUCCESS,
        severity=AuditSeverity.INFO,
    )

    deleted = service.cleanup_old_logs(days_old=30)
    assert deleted == 1


def test_log_event_failure_does_not_raise(monkeypatch, db_session):
    service = AuditService(db_session)
    monkeypatch.setattr(db_session, "commit", MagicMock(side_effect=Exception("db failure")))

    result = service.log_event(
        event_category=AuditEventCategory.SYSTEM,
        event_type="failure",
        outcome=AuditOutcome.FAILURE,
    )

    assert result is None
