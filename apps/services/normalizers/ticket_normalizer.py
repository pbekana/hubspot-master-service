"""
Ticket normalizer for HubSpot ticket records.
"""
import logging
from typing import List, Dict, Any
from datetime import datetime
import pandas as pd

logger = logging.getLogger(__name__)


class TicketNormalizer:
    """Normalizes HubSpot ticket records into flat table structure."""
    
    def normalize(self, raw_tickets: List[Dict[str, Any]]) -> pd.DataFrame:
        """
        Normalize raw HubSpot ticket records.
        
        Args:
            raw_tickets: List of raw ticket records from HubSpot API
        
        Returns:
            pandas DataFrame with normalized ticket data
        """
        if not raw_tickets:
            return pd.DataFrame()
        
        records = []
        extraction_time = datetime.utcnow()
        
        for ticket in raw_tickets:
            try:
                props = ticket.get("properties", {})
                
                # Extract core properties
                record = {
                    # Identifiers
                    "id": ticket.get("id"),
                    "hs_object_id": props.get("hs_object_id"),
                    "hs_ticket_id": props.get("hs_ticket_id"),
                    
                    # Ticket information
                    "subject": props.get("subject"),
                    "content": props.get("content"),
                    "hs_pipeline": props.get("hs_pipeline"),
                    "hs_pipeline_stage": props.get("hs_pipeline_stage"),
                    
                    # Status and priority
                    "hs_ticket_priority": props.get("hs_ticket_priority"),
                    "hs_ticket_category": props.get("hs_ticket_category"),
                    
                    # Ownership
                    "hubspot_owner_id": props.get("hubspot_owner_id"),
                    "hubspot_team_id": props.get("hubspot_team_id"),
                    
                    # Source
                    "source_type": props.get("source_type"),
                    "hs_created_by_user_id": props.get("hs_created_by_user_id"),
                    
                    # Dates
                    "createdate": props.get("createdate"),
                    "hs_lastmodifieddate": props.get("hs_lastmodifieddate"),
                    "closed_date": props.get("closed_date"),
                    "hs_resolution": props.get("hs_resolution"),
                    
                    # Time tracking
                    "time_to_close": props.get("time_to_close"),
                    "time_to_first_response": props.get("time_to_first_response"),
                    
                    # Timestamps from HubSpot
                    "created_at": ticket.get("createdAt"),
                    "updated_at": ticket.get("updatedAt"),
                    "archived": ticket.get("archived", False),
                    
                    # Extraction metadata
                    "_extracted_at": extraction_time,
                }
                
                # Store remaining properties as JSON for flexibility
                excluded_keys = set(record.keys()) - {"_extracted_at"}
                extra_props = {k: v for k, v in props.items() if k not in excluded_keys}
                record["_extra_properties"] = str(extra_props) if extra_props else None
                
                records.append(record)
                
            except Exception as e:
                logger.warning(f"Failed to normalize ticket {ticket.get('id')}: {str(e)}")
                continue
        
        df = pd.DataFrame(records)
        logger.info(f"Normalized {len(df)} tickets")
        return df
