"""MinIO client for uploading normalized data."""
import logging
from pathlib import Path
from typing import Dict, Any
from datetime import datetime
from minio import Minio
from minio.error import S3Error
from apps.config import settings
from apps.utils.retry import retry_with_backoff

logger = logging.getLogger(__name__)


class MinIOClient:
    """Client for MinIO object storage."""
    
    def __init__(self):
        """Initialize MinIO client."""
        self.client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        self.bucket = settings.minio_bucket
    
    def ensure_bucket_exists(self):
        """Ensure the bucket exists, create if it doesn't."""
        try:
            if not self.client.bucket_exists(self.bucket):
                logger.info(f"Creating MinIO bucket: {self.bucket}")
                self.client.make_bucket(self.bucket)
            else:
                logger.debug(f"MinIO bucket exists: {self.bucket}")
        except S3Error as e:
            logger.error(f"Failed to ensure bucket exists: {str(e)}")
            raise
    
    async def upload_file(
        self,
        local_path: str,
        object_key: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        """
        Upload a file to MinIO.
        
        Args:
            local_path: Path to local file
            object_key: Object key in MinIO
            content_type: Content type of the file
        
        Returns:
            Object key of uploaded file
        
        Raises:
            FileNotFoundError: If local file doesn't exist
            S3Error: If upload fails
        """
        local_file = Path(local_path)
        if not local_file.exists():
            raise FileNotFoundError(f"Local file not found: {local_path}")
        
        logger.info(f"Uploading {local_path} to MinIO: {object_key}")
        
        async def _upload():
            self.ensure_bucket_exists()
            
            self.client.fput_object(
                bucket_name=self.bucket,
                object_name=object_key,
                file_path=str(local_file),
                content_type=content_type,
            )
            
            return object_key
        
        try:
            result = await retry_with_backoff(_upload)
            logger.info(f"Successfully uploaded to MinIO: {object_key}")
            return result
        except Exception as e:
            logger.error(f"Failed to upload to MinIO: {str(e)}")
            raise
    
    async def upload_normalized_data(
        self,
        scan_id: int,
        organization_id: str,
        processing_date: datetime,
        tables: Dict[str, str],
    ) -> Dict[str, str]:
        """
        Upload normalized data tables to MinIO.
        
        Uses organization structure:
        hubspot/{table_name}/glynac_organization_id={org_id}/processing_date={date}/{table}.parquet
        
        Args:
            scan_id: Scan/job ID
            organization_id: Organization ID
            processing_date: Processing date
            tables: Dict mapping table name to local file path
        
        Returns:
            Dict mapping table name to MinIO object key
        
        Raises:
            S3Error: If upload fails
        """
        uploaded_objects = {}
        date_str = processing_date.strftime("%Y-%m-%d")
        
        for table_name, local_path in tables.items():
            # Build object key following the required structure
            object_key = (
                f"hubspot/{table_name}/"
                f"glynac_organization_id={organization_id}/"
                f"processing_date={date_str}/"
                f"{table_name}.parquet"
            )
            
            try:
                uploaded_key = await self.upload_file(
                    local_path=local_path,
                    object_key=object_key,
                    content_type="application/parquet",
                )
                uploaded_objects[table_name] = uploaded_key
            except Exception as e:
                logger.error(f"Failed to upload table {table_name}: {str(e)}")
                raise
        
        logger.info(f"Uploaded {len(uploaded_objects)} tables for scan {scan_id}")
        return uploaded_objects
    
    def list_objects(self, prefix: str = ""):
        """
        List objects in bucket with optional prefix.
        
        Args:
            prefix: Object key prefix
        
        Returns:
            Iterator of object information
        """
        try:
            self.ensure_bucket_exists()
            return self.client.list_objects(self.bucket, prefix=prefix, recursive=True)
        except S3Error as e:
            logger.error(f"Failed to list objects: {str(e)}")
            raise
    
    def delete_object(self, object_key: str):
        """
        Delete an object from MinIO.
        
        Args:
            object_key: Object key to delete
        
        Raises:
            S3Error: If delete fails
        """
        try:
            self.client.remove_object(self.bucket, object_key)
            logger.info(f"Deleted object from MinIO: {object_key}")
        except S3Error as e:
            logger.error(f"Failed to delete object: {str(e)}")
            raise
