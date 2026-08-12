"""
Contact normalizer for HubSpot contact records.
"""
import logging
from typing import List, Dict, Any
from datetime import datetime
import pandas as pd

logger = logging.getLogger(__name__)


class ContactNormalizer:
    """Normalizes HubSpot contact records into flat table structure."""
    
    def normalize(self, raw_contacts: List[Dict[str, Any]]) -> pd.DataFrame:
        """
        Normalize raw HubSpot contact records.
        
        Args:
            raw_contacts: List of raw contact records from HubSpot API
        
        Returns:
            pandas DataFrame with normalized contact data
        """
        if not raw_contacts:
            return pd.DataFrame()
        
        records = []
        extraction_time = datetime.utcnow()
        
        for contact in raw_contacts:
            try:
                props = contact.get("properties", {})
                
                # Extract core properties
                record = {
                    # Identifiers
                    "id": contact.get("id"),
                    "hs_object_id": props.get("hs_object_id"),
                    
                    # Contact information
                    "email": props.get("email"),
                    "firstname": props.get("firstname"),
                    "lastname": props.get("lastname"),
                    "phone": props.get("phone"),
                    "mobilephone": props.get("mobilephone"),
                    "website": props.get("website"),
                    
                    # Company association
                    "company": props.get("company"),
                    "jobtitle": props.get("jobtitle"),
                    
                    # Address fields
                    "address": props.get("address"),
                    "city": props.get("city"),
                    "state": props.get("state"),
                    "zip": props.get("zip"),
                    "country": props.get("country"),
                    
                    # Lifecycle
                    "lifecyclestage": props.get("lifecyclestage"),
                    "hs_lead_status": props.get("hs_lead_status"),
                    
                    # System fields
                    "createdate": props.get("createdate"),
                    "lastmodifieddate": props.get("lastmodifieddate"),
                    "hs_email_domain": props.get("hs_email_domain"),
                    
                    # Timestamps from HubSpot
                    "created_at": contact.get("createdAt"),
                    "updated_at": contact.get("updatedAt"),
                    "archived": contact.get("archived", False),
                    
                    # Extraction metadata
                    "_extracted_at": extraction_time,
                }
                
                # Store remaining properties as JSON for flexibility
                excluded_keys = set(record.keys()) - {"_extracted_at"}
                extra_props = {k: v for k, v in props.items() if k not in excluded_keys}
                record["_extra_properties"] = str(extra_props) if extra_props else None
                
                records.append(record)
                
            except Exception as e:
                logger.warning(f"Failed to normalize contact {contact.get('id')}: {str(e)}")
                continue
        
        df = pd.DataFrame(records)
        logger.info(f"Normalized {len(df)} contacts")
        return df
