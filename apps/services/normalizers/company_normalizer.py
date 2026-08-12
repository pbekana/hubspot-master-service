"""
Company normalizer for HubSpot company records.
"""
import logging
from typing import List, Dict, Any
from datetime import datetime
import pandas as pd

logger = logging.getLogger(__name__)


class CompanyNormalizer:
    """Normalizes HubSpot company records into flat table structure."""
    
    def normalize(self, raw_companies: List[Dict[str, Any]]) -> pd.DataFrame:
        """
        Normalize raw HubSpot company records.
        
        Args:
            raw_companies: List of raw company records from HubSpot API
        
        Returns:
            pandas DataFrame with normalized company data
        """
        if not raw_companies:
            return pd.DataFrame()
        
        records = []
        extraction_time = datetime.utcnow()
        
        for company in raw_companies:
            try:
                props = company.get("properties", {})
                
                # Extract core properties
                record = {
                    # Identifiers
                    "id": company.get("id"),
                    "hs_object_id": props.get("hs_object_id"),
                    
                    # Company information
                    "name": props.get("name"),
                    "domain": props.get("domain"),
                    "website": props.get("website"),
                    "description": props.get("description"),
                    
                    # Industry & classification
                    "industry": props.get("industry"),
                    "type": props.get("type"),
                    "numberofemployees": props.get("numberofemployees"),
                    "annualrevenue": props.get("annualrevenue"),
                    
                    # Contact information
                    "phone": props.get("phone"),
                    
                    # Address fields
                    "address": props.get("address"),
                    "address2": props.get("address2"),
                    "city": props.get("city"),
                    "state": props.get("state"),
                    "zip": props.get("zip"),
                    "country": props.get("country"),
                    
                    # Lifecycle
                    "lifecyclestage": props.get("lifecyclestage"),
                    "hs_lead_status": props.get("hs_lead_status"),
                    
                    # System fields
                    "createdate": props.get("createdate"),
                    "hs_lastmodifieddate": props.get("hs_lastmodifieddate"),
                    
                    # Timestamps from HubSpot
                    "created_at": company.get("createdAt"),
                    "updated_at": company.get("updatedAt"),
                    "archived": company.get("archived", False),
                    
                    # Extraction metadata
                    "_extracted_at": extraction_time,
                }
                
                # Store remaining properties as JSON for flexibility
                excluded_keys = set(record.keys()) - {"_extracted_at"}
                extra_props = {k: v for k, v in props.items() if k not in excluded_keys}
                record["_extra_properties"] = str(extra_props) if extra_props else None
                
                records.append(record)
                
            except Exception as e:
                logger.warning(f"Failed to normalize company {company.get('id')}: {str(e)}")
                continue
        
        df = pd.DataFrame(records)
        logger.info(f"Normalized {len(df)} companies")
        return df
