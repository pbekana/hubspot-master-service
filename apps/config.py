"""
Configuration management for HubSpot Master Service.
Uses environment variables with Pydantic settings.
"""
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False
    )
    
    # Application
    app_env: str = Field(default="development", description="Application environment")
    log_level: str = Field(default="INFO", description="Logging level")
    
    # Database
    database_url: str = Field(..., description="PostgreSQL connection URL")
    
    # HubSpot API
    hubspot_client_id: str = Field(..., description="HubSpot OAuth client ID")
    hubspot_client_secret: str = Field(..., description="HubSpot OAuth client secret")
    hubspot_api_base_url: str = Field(default="https://api.hubapi.com", description="HubSpot API base URL")
    hubspot_api_version: str = Field(default="v3", description="HubSpot API version")
    hubspot_burst_limit: int = Field(default=100, description="HubSpot burst request limit")
    hubspot_daily_limit: int = Field(default=500000, description="HubSpot daily request limit")
    hubspot_rate_limit_window_seconds: int = Field(default=10, description="Rate limit window in seconds")
    hubspot_default_retry_after: int = Field(default=5, description="Default retry after in seconds")
    hubspot_default_page_size: int = Field(default=100, description="Default page size for pagination")
    hubspot_max_page_size: int = Field(default=100, description="Maximum page size")
    
    # MinIO
    minio_endpoint: str = Field(..., description="MinIO endpoint")
    minio_bucket: str = Field(default="hubspot-data", description="MinIO bucket name")
    minio_access_key: str = Field(..., description="MinIO access key")
    minio_secret_key: str = Field(..., description="MinIO secret key")
    minio_secure: bool = Field(default=False, description="Use HTTPS for MinIO")
    
    # External call retry
    external_call_max_retries: int = Field(default=3, description="Max retries for external calls")
    external_call_retry_delays: str = Field(default="1,2,4", description="Retry delays in seconds")
    external_call_jitter: float = Field(default=0.5, description="Jitter factor for retries")
    
    # Dead letter queue
    dlq_payload_max_bytes: int = Field(default=65536, description="Max payload size for DLQ")
    
    # HMAC authentication
    hmac_enabled: bool = Field(default=True, description="Enable HMAC authentication")
    hmac_secret_key_core: str = Field(default="", description="HMAC secret for coordinator")
    hmac_secret_key_engineer: str = Field(default="", description="HMAC secret for read-only engineer access")
    hmac_signature_max_age: int = Field(default=300, description="Max age of HMAC signature in seconds")
    
    @property
    def retry_delays(self) -> List[int]:
        """Parse retry delays from comma-separated string."""
        return [int(d.strip()) for d in self.external_call_retry_delays.split(",")]


# Global settings instance
settings = Settings()
