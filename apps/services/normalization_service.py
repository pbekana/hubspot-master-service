"""
Normalization service for transforming raw HubSpot data into normalized tables.
"""
import logging
import os
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from apps.models.job import Job, JobStatus
from apps.services.normalizers import (
    ContactNormalizer,
    CompanyNormalizer,
    DealNormalizer,
    TicketNormalizer,
    OwnerNormalizer,
)
from apps.clients.minio_client import MinIOClient

logger = logging.getLogger(__name__)


class NormalizationService:
    """Service for normalizing extracted HubSpot data."""
    
    # Supported object types
    SUPPORTED_OBJECTS = ["contacts", "companies", "deals", "tickets", "owners"]
    
    def __init__(self, db: Session):
        self.db = db
        self.normalizers = {
            "contacts": ContactNormalizer(),
            "companies": CompanyNormalizer(),
            "deals": DealNormalizer(),
            "tickets": TicketNormalizer(),
            "owners": OwnerNormalizer(),
        }
        self.minio_client = MinIOClient()
        
        # Create local data directory for temporary files
        self.data_dir = Path("./data")
        self.data_dir.mkdir(exist_ok=True)
    
    async def normalize_scan(
        self,
        scan_id: int,
        output_format: str = "parquet",
        upload_to_minio: bool = True,
    ) -> Dict[str, Any]:
        """
        Normalize data from a completed scan.
        
        Args:
            scan_id: Job/scan ID
            output_format: Output format (json or parquet)
            upload_to_minio: Whether to upload to MinIO
        
        Returns:
            Dictionary with normalization results
        """
        # Get job
        job = self.db.query(Job).filter(Job.id == scan_id).first()
        if not job:
            raise ValueError(f"Scan {scan_id} not found")
        
        if job.status != JobStatus.COMPLETED:
            raise ValueError(f"Scan {scan_id} is not completed (status: {job.status})")
        
        try:
            # Update job status
            job.status = JobStatus.NORMALIZING
            self.db.commit()
            
            # Load raw data (in real implementation, would load from storage)
            # For now, we'll assume raw data is stored somewhere
            # This is a placeholder - in production, load from wherever _extract_object_type saved it
            raw_data = self._load_raw_data(scan_id, job.object_types)
            
            # Normalize each object type
            normalized_tables = {}
            local_files = {}
            
            for object_type in job.object_types:
                if object_type not in raw_data or not raw_data[object_type]:
                    logger.warning(f"No raw data found for {object_type}, skipping")
                    continue
                
                # Normalize data
                tables = self._normalize_object_type(
                    object_type=object_type,
                    raw_data=raw_data[object_type],
                )
                
                # Save to disk
                for table_name, df in tables.items():
                    if df.empty:
                        logger.info(f"Skipping empty table: {table_name}")
                        continue
                    
                    file_path = self._save_table(
                        scan_id=scan_id,
                        table_name=table_name,
                        df=df,
                        output_format=output_format,
                    )
                    
                    local_files[table_name] = file_path
                    normalized_tables[table_name] = len(df)
            
            # Upload to MinIO if requested
            minio_objects = None
            if upload_to_minio and local_files:
                job.status = JobStatus.UPLOADING_TO_MINIO
                self.db.commit()
                
                processing_date = datetime.utcnow()
                minio_objects = await self.minio_client.upload_normalized_data(
                    scan_id=scan_id,
                    organization_id=job.organization_id,
                    processing_date=processing_date,
                    tables=local_files,
                )
                
                job.minio_uploaded_at = datetime.utcnow()
            
            # Update job status
            job.status = JobStatus.COMPLETED
            job.normalized_at = datetime.utcnow()
            self.db.commit()
            
            logger.info(f"Normalization completed for scan {scan_id}")
            
            return {
                "scan_id": scan_id,
                "tables": list(normalized_tables.keys()),
                "table_sizes": normalized_tables,
                "status": "completed",
                "minio_objects": minio_objects,
                "output_format": output_format,
            }
        
        except Exception as e:
            logger.error(f"Normalization failed for scan {scan_id}: {str(e)}", exc_info=True)
            job.status = JobStatus.FAILED
            job.error_message = f"Normalization failed: {str(e)}"
            self.db.commit()
            raise
    
    def _normalize_object_type(
        self,
        object_type: str,
        raw_data: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Normalize a single object type.
        
        Args:
            object_type: HubSpot object type
            raw_data: Raw data from HubSpot
        
        Returns:
            Dictionary of table_name -> DataFrame
        """
        normalizer = self.normalizers.get(object_type)
        if not normalizer:
            raise ValueError(f"No normalizer found for {object_type}")
        
        result = normalizer.normalize(raw_data)
        
        # Deal normalizer returns dict, others return DataFrame
        if isinstance(result, dict):
            return result
        else:
            return {object_type: result}
    
    def _save_table(
        self,
        scan_id: int,
        table_name: str,
        df: Any,  # pandas DataFrame
        output_format: str,
    ) -> str:
        """
        Save table to disk.
        
        Args:
            scan_id: Scan ID
            table_name: Table name
            df: pandas DataFrame
            output_format: Output format (json or parquet)
        
        Returns:
            Path to saved file
        """
        # Create scan directory
        scan_dir = self.data_dir / f"scan_{scan_id}"
        scan_dir.mkdir(exist_ok=True)
        
        if output_format == "parquet":
            file_path = scan_dir / f"{table_name}.parquet"
            df.to_parquet(
                str(file_path),
                engine="pyarrow",
                compression="snappy",
                index=False,
            )
        elif output_format == "json":
            file_path = scan_dir / f"{table_name}.json"
            df.to_json(
                str(file_path),
                orient="records",
                lines=True,  # JSON Lines format
            )
        else:
            raise ValueError(f"Unsupported output format: {output_format}")
        
        logger.info(f"Saved {table_name} to {file_path} ({len(df)} records)")
        return str(file_path)
    
    def _load_raw_data(
        self,
        scan_id: int,
        object_types: List[str],
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Load raw data for scan.
        
        In production, this would load from wherever the extraction service saved it.
        For now, returns empty dict as placeholder.
        
        Args:
            scan_id: Scan ID
            object_types: Object types to load
        
        Returns:
            Dictionary mapping object_type -> list of raw records
        """
        # TODO: Implement loading raw data from storage
        # This is a placeholder. In production:
        # 1. Check if raw data exists for this scan
        # 2. Load from disk/database/S3 where extraction service saved it
        # 3. Return the raw records
        
        # For now, return empty structure
        logger.warning(
            f"Raw data loading not implemented. Returning empty data for scan {scan_id}"
        )
        return {obj_type: [] for obj_type in object_types}
    
    def get_available_tables(self, scan_id: int) -> List[str]:
        """
        Get list of available normalized tables for a scan.
        
        Args:
            scan_id: Scan ID
        
        Returns:
            List of table names
        """
        scan_dir = self.data_dir / f"scan_{scan_id}"
        if not scan_dir.exists():
            return []
        
        tables = []
        for file_path in scan_dir.glob("*.parquet"):
            tables.append(file_path.stem)
        for file_path in scan_dir.glob("*.json"):
            tables.append(file_path.stem)
        
        return sorted(set(tables))
    
    @staticmethod
    def get_supported_objects() -> List[str]:
        """Get list of supported object types."""
        return NormalizationService.SUPPORTED_OBJECTS.copy()
