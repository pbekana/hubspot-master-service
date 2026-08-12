"""
Owner normalizer for HubSpot owner records.
"""
import logging
from typing import List, Dict, Any
from datetime import datetime
import pandas as pd

logger = logging.getLogger(__name__)


class OwnerNormalizer:
    """Normalizes HubSpot owner records into flat table structure."""
    
    def normalize(self, raw_owners: List[Dict[str, Any]]) -> pd.DataFrame:
        """
        Normalize raw HubSpot owner records.
        
        Args:
            raw_owners: List of raw owner records from HubSpot API
        
        Returns:
            pandas DataFrame with normalized owner data
        """
        if not raw_owners:
            return pd.DataFrame()
        
        records = []
        extraction_time = datetime.utcnow()
        
        for owner in raw_owners:
            try:
                props = owner.get("properties", {})
                
                # Extract core properties
                record = {
                    # Identifiers
                    "id": owner.get("id"),
                    "hs_object_id": props.get("hs_object_id"),
                    "ownerId": owner.get("ownerId"),  # Sometimes ID is at root level
                    
                    # Owner information
                    "email": owner.get("email") or props.get("email"),
                    "firstName": owner.get("firstName") or props.get("firstName"),
                    "lastName": owner.get("lastName") or props.get("lastName"),
                    
                    # Type and status
                    "type": owner.get("type") or props.get("type"),
                    "archived": owner.get("archived", False),
                    
                    # User ID
                    "userId": owner.get("userId") or props.get("userId"),
                    
                    # Teams
                    "teams": str(owner.get("teams", [])) if owner.get("teams") else None,
                    
                    # Timestamps from HubSpot
                    "created_at": owner.get("createdAt") or props.get("createdAt"),
                    "updated_at": owner.get("updatedAt") or props.get("updatedAt"),
                    
                    # Extraction metadata
                    "_extracted_at": extraction_time,
                }
                
                # Store remaining properties as JSON for flexibility
                excluded_keys = set(record.keys()) - {"_extracted_at"}
                extra_props = {k: v for k, v in props.items() if k not in excluded_keys}
                # Also include root-level fields
                for key in ["remoteList", "activeUserId", "hasContactsAccess"]:
                    if key in owner and key not in excluded_keys:
                        extra_props[key] = owner[key]
                
                record["_extra_properties"] = str(extra_props) if extra_props else None
                
                records.append(record)
                
            except Exception as e:
                logger.warning(f"Failed to normalize owner {owner.get('id')}: {str(e)}")
                continue
        
        df = pd.DataFrame(records)
        logger.info(f"Normalized {len(df)} owners")
        return df
