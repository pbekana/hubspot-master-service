"""
Extraction service for managing HubSpot data extraction jobs.
"""
import logging
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from apps.models.job import Job, JobStatus
from apps.models.checkpoint import Checkpoint
from apps.clients.hubspot_api import HubSpotAPIClient
from apps.clients.hubspot_auth import HubSpotAuthClient
from apps.utils.dlq import write_to_dlq

logger = logging.getLogger(__name__)


class ExtractionService:
    """Service for extraction job management."""
    
    def __init__(self, db: Session):
        self.db = db
        self.auth_client = HubSpotAuthClient()
        self._pause_flags = {}  # job_id -> bool
        self._cancel_flags = {}  # job_id -> bool
    
    def start_scan(
        self,
        organization_id: str,
        object_types: List[str],
        access_token: str,
        refresh_token: Optional[str] = None,
    ) -> Job:
        """
        Start a new extraction scan.
        
        Args:
            organization_id: Organization ID
            object_types: List of HubSpot object types to extract
            access_token: OAuth access token
            refresh_token: Optional refresh token
        
        Returns:
            Created Job
        """
        # Create job
        job = Job(
            organization_id=organization_id,
            status=JobStatus.PENDING,
            object_types=object_types,
            entity_record_counts={},
            access_token_encrypted=access_token,  # TODO: Encrypt in production
            refresh_token_encrypted=refresh_token,
            last_heartbeat=datetime.utcnow(),
        )
        
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        
        logger.info(f"Created scan job {job.id} for org {organization_id}")
        
        # Start execution in background (in production, use task queue)
        asyncio.create_task(self._execute_scan(job.id))
        
        return job
    
    async def _execute_scan(self, job_id: int):
        """
        Execute extraction scan.
        
        Args:
            job_id: Job ID
        """
        job = self.db.query(Job).filter(Job.id == job_id).first()
        if not job:
            logger.error(f"Job {job_id} not found")
            return
        
        try:
            # Update status to running
            job.status = JobStatus.RUNNING
            job.last_heartbeat = datetime.utcnow()
            self.db.commit()
            
            # Create API client
            api_client = HubSpotAPIClient(job.access_token_encrypted)
            
            # Extract each object type
            for object_type in job.object_types:
                # Check for pause/cancel
                if self._should_pause(job_id):
                    job.status = JobStatus.PAUSED
                    self.db.commit()
                    logger.info(f"Job {job_id} paused")
                    return
                
                if self._should_cancel(job_id):
                    job.status = JobStatus.CANCELLED
                    self.db.commit()
                    logger.info(f"Job {job_id} cancelled")
                    return
                
                # Get checkpoint
                checkpoint = self._get_or_create_checkpoint(job_id, object_type)
                
                # Extract pages
                total_records = await self._extract_object_type(
                    job_id,
                    object_type,
                    api_client,
                    checkpoint,
                )
                
                # Update record count
                if not job.entity_record_counts:
                    job.entity_record_counts = {}
                job.entity_record_counts[object_type] = total_records
                self.db.commit()
            
            # Mark as completed
            job.status = JobStatus.COMPLETED
            job.last_heartbeat = datetime.utcnow()
            self.db.commit()
            
            logger.info(f"Job {job_id} completed successfully")
            
        except Exception as e:
            logger.error(f"Job {job_id} failed: {str(e)}", exc_info=True)
            job.status = JobStatus.FAILED
            job.error_message = str(e)
            self.db.commit()
            
            # Write to DLQ
            write_to_dlq(
                db=self.db,
                target_service="hubspot",
                operation="extract_scan",
                payload={"job_id": job_id},
                attempts=1,
                error=e,
                organization_id=job.organization_id,
                scan_id=job_id,
            )
    
    async def _extract_object_type(
        self,
        job_id: int,
        object_type: str,
        api_client: HubSpotAPIClient,
        checkpoint: Checkpoint,
    ) -> int:
        """
        Extract all pages for an object type.
        
        Args:
            job_id: Job ID
            object_type: Object type to extract
            api_client: HubSpot API client
            checkpoint: Checkpoint for this object type
        
        Returns:
            Total number of records extracted
        """
        logger.info(f"Extracting {object_type} for job {job_id}")
        
        after_cursor = checkpoint.cursor
        total_records = checkpoint.records_processed
        
        while True:
            # Check for pause/cancel
            if self._should_pause(job_id) or self._should_cancel(job_id):
                break
            
            # Update heartbeat
            self._update_heartbeat(job_id)
            
            # Fetch page
            try:
                page_data = await api_client.get_page(
                    object_type=object_type,
                    after_cursor=after_cursor,
                )
            except Exception as e:
                logger.error(f"Failed to fetch page for {object_type}: {str(e)}")
                raise
            
            records = page_data.get("results", [])
            total_records += len(records)
            
            # TODO: Save raw records to disk/database
            
            # Get next cursor
            paging = page_data.get("paging", {})
            next_cursor = paging.get("next", {}).get("after")
            
            # Update checkpoint
            checkpoint.cursor = next_cursor
            checkpoint.records_processed = total_records
            checkpoint.last_updated_at = datetime.utcnow()
            self.db.commit()
            
            logger.info(f"Processed page for {object_type}: {len(records)} records (total: {total_records})")
            
            # Check if we're done
            if not next_cursor:
                logger.info(f"Completed extraction of {object_type}: {total_records} records")
                break
            
            after_cursor = next_cursor
        
        return total_records
    
    def _get_or_create_checkpoint(self, job_id: int, object_type: str) -> Checkpoint:
        """Get or create checkpoint for job and object type."""
        checkpoint = self.db.query(Checkpoint).filter(
            Checkpoint.job_id == job_id,
            Checkpoint.object_type == object_type,
        ).first()
        
        if not checkpoint:
            checkpoint = Checkpoint(
                job_id=job_id,
                object_type=object_type,
                cursor=None,
                records_processed=0,
            )
            self.db.add(checkpoint)
            self.db.commit()
        
        return checkpoint
    
    def _update_heartbeat(self, job_id: int):
        """Update job heartbeat."""
        job = self.db.query(Job).filter(Job.id == job_id).first()
        if job:
            job.last_heartbeat = datetime.utcnow()
            self.db.commit()
    
    def _should_pause(self, job_id: int) -> bool:
        """Check if job should pause."""
        return self._pause_flags.get(job_id, False)
    
    def _should_cancel(self, job_id: int) -> bool:
        """Check if job should be cancelled."""
        return self._cancel_flags.get(job_id, False)
    
    def pause_scan(self, job_id: int) -> Job:
        """Pause a running scan."""
        job = self.db.query(Job).filter(Job.id == job_id).first()
        if not job:
            raise ValueError(f"Job {job_id} not found")
        
        if job.status != JobStatus.RUNNING:
            raise ValueError(f"Job {job_id} is not running (status: {job.status})")
        
        self._pause_flags[job_id] = True
        logger.info(f"Pause requested for job {job_id}")
        return job
    
    def resume_scan(self, job_id: int) -> Job:
        """Resume a paused scan."""
        job = self.db.query(Job).filter(Job.id == job_id).first()
        if not job:
            raise ValueError(f"Job {job_id} not found")
        
        if job.status != JobStatus.PAUSED:
            raise ValueError(f"Job {job_id} is not paused (status: {job.status})")
        
        # Clear pause flag and restart
        self._pause_flags[job_id] = False
        job.status = JobStatus.RESUMING
        self.db.commit()
        
        # Restart execution
        asyncio.create_task(self._execute_scan(job_id))
        
        logger.info(f"Job {job_id} resumed")
        return job
    
    def cancel_scan(self, job_id: int) -> Job:
        """Cancel a scan."""
        job = self.db.query(Job).filter(Job.id == job_id).first()
        if not job:
            raise ValueError(f"Job {job_id} not found")
        
        if job.status in [JobStatus.COMPLETED, JobStatus.CANCELLED, JobStatus.FAILED]:
            raise ValueError(f"Job {job_id} is already in terminal state: {job.status}")
        
        self._cancel_flags[job_id] = True
        logger.info(f"Cancel requested for job {job_id}")
        return job
    
    def get_scan_status(self, job_id: int) -> Job:
        """Get scan status."""
        job = self.db.query(Job).filter(Job.id == job_id).first()
        if not job:
            raise ValueError(f"Job {job_id} not found")
        return job
    
    def list_scans(
        self,
        organization_id: Optional[str] = None,
        status: Optional[JobStatus] = None,
        limit: int = 100,
    ) -> List[Job]:
        """List scans with optional filters."""
        query = self.db.query(Job)
        
        if organization_id:
            query = query.filter(Job.organization_id == organization_id)
        if status:
            query = query.filter(Job.status == status)
        
        return query.order_by(Job.created_at.desc()).limit(limit).all()
    
    def detect_crashed_jobs(self, timeout_minutes: int = 30) -> List[Job]:
        """
        Detect crashed jobs based on stale heartbeat.
        
        Args:
            timeout_minutes: Minutes without heartbeat to consider crashed
        
        Returns:
            List of crashed jobs
        """
        cutoff_time = datetime.utcnow() - timedelta(minutes=timeout_minutes)
        
        crashed_jobs = self.db.query(Job).filter(
            Job.status == JobStatus.RUNNING,
            Job.last_heartbeat < cutoff_time,
        ).all()
        
        for job in crashed_jobs:
            job.status = JobStatus.CRASHED
            logger.warning(f"Job {job.id} marked as crashed (last heartbeat: {job.last_heartbeat})")
        
        self.db.commit()
        
        return crashed_jobs
    
    def remove_scan(self, job_id: int):
        """Remove a scan and its checkpoints."""
        job = self.db.query(Job).filter(Job.id == job_id).first()
        if not job:
            raise ValueError(f"Job {job_id} not found")
        
        # Delete checkpoints
        self.db.query(Checkpoint).filter(Checkpoint.job_id == job_id).delete()
        
        # Delete job
        self.db.delete(job)
        self.db.commit()
        
        logger.info(f"Removed job {job_id}")
