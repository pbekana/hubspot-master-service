"""
Deal normalizer for HubSpot deal records.
Produces multiple tables: deals, deal_line_items, deal_associations.
"""
import logging
from typing import List, Dict, Any, Tuple
from datetime import datetime
import pandas as pd

logger = logging.getLogger(__name__)


class DealNormalizer:
    """Normalizes HubSpot deal records into multiple related tables."""
    
    def normalize(self, raw_deals: List[Dict[str, Any]]) -> Dict[str, pd.DataFrame]:
        """
        Normalize raw HubSpot deal records into multiple tables.
        
        Args:
            raw_deals: List of raw deal records from HubSpot API
        
        Returns:
            Dictionary with table names as keys and DataFrames as values:
            - deals: Main deal information
            - deal_line_items: Line items for deals (if present)
            - deal_associations: Associations to other objects
        """
        if not raw_deals:
            return {
                "deals": pd.DataFrame(),
                "deal_line_items": pd.DataFrame(),
                "deal_associations": pd.DataFrame(),
            }
        
        deals = []
        line_items = []
        associations = []
        extraction_time = datetime.utcnow()
        
        for deal in raw_deals:
            try:
                deal_id = deal.get("id")
                props = deal.get("properties", {})
                
                # Main deal record
                deal_record = {
                    # Identifiers
                    "id": deal_id,
                    "hs_object_id": props.get("hs_object_id"),
                    
                    # Deal information
                    "dealname": props.get("dealname"),
                    "dealstage": props.get("dealstage"),
                    "pipeline": props.get("pipeline"),
                    "amount": props.get("amount"),
                    "closedate": props.get("closedate"),
                    
                    # Deal type and priority
                    "dealtype": props.get("dealtype"),
                    "hs_priority": props.get("hs_priority"),
                    
                    # Forecast
                    "hs_forecast_amount": props.get("hs_forecast_amount"),
                    "hs_forecast_probability": props.get("hs_forecast_probability"),
                    
                    # Deal description
                    "description": props.get("description"),
                    
                    # System fields
                    "createdate": props.get("createdate"),
                    "hs_lastmodifieddate": props.get("hs_lastmodifieddate"),
                    "hs_closed_amount": props.get("hs_closed_amount"),
                    "hs_is_closed": props.get("hs_is_closed"),
                    "hs_deal_stage_probability": props.get("hs_deal_stage_probability"),
                    
                    # Timestamps from HubSpot
                    "created_at": deal.get("createdAt"),
                    "updated_at": deal.get("updatedAt"),
                    "archived": deal.get("archived", False),
                    
                    # Extraction metadata
                    "_extracted_at": extraction_time,
                }
                
                # Store remaining properties as JSON
                excluded_keys = set(deal_record.keys()) - {"_extracted_at"}
                extra_props = {k: v for k, v in props.items() if k not in excluded_keys}
                deal_record["_extra_properties"] = str(extra_props) if extra_props else None
                
                deals.append(deal_record)
                
                # Extract line items if present
                deal_line_items = deal.get("line_items", [])
                for idx, line_item in enumerate(deal_line_items):
                    line_item_record = {
                        "deal_id": deal_id,
                        "line_item_index": idx,
                        "name": line_item.get("name"),
                        "quantity": line_item.get("quantity"),
                        "price": line_item.get("price"),
                        "amount": line_item.get("amount"),
                        "hs_product_id": line_item.get("hs_product_id"),
                        "hs_sku": line_item.get("hs_sku"),
                        "_extracted_at": extraction_time,
                    }
                    line_items.append(line_item_record)
                
                # Extract associations if present
                deal_associations = deal.get("associations", {})
                for assoc_type, assoc_list in deal_associations.items():
                    if isinstance(assoc_list, list):
                        for assoc in assoc_list:
                            assoc_record = {
                                "deal_id": deal_id,
                                "association_type": assoc_type,
                                "associated_id": assoc.get("id"),
                                "association_category": assoc.get("type"),
                                "_extracted_at": extraction_time,
                            }
                            associations.append(assoc_record)
                
            except Exception as e:
                logger.warning(f"Failed to normalize deal {deal.get('id')}: {str(e)}")
                continue
        
        deals_df = pd.DataFrame(deals)
        line_items_df = pd.DataFrame(line_items) if line_items else pd.DataFrame()
        associations_df = pd.DataFrame(associations) if associations else pd.DataFrame()
        
        logger.info(
            f"Normalized {len(deals_df)} deals, "
            f"{len(line_items_df)} line items, "
            f"{len(associations_df)} associations"
        )
        
        return {
            "deals": deals_df,
            "deal_line_items": line_items_df,
            "deal_associations": associations_df,
        }
