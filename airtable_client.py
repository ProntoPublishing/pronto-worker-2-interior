"""
Airtable Client
===============

Interacts with Airtable Services table.

Author: Pronto Publishing
Version: 1.0.0
"""

import os
import logging
from typing import Dict, Any, Optional
from pyairtable import Api

logger = logging.getLogger(__name__)


class AirtableClient:
    """Client for Airtable Services table."""
    
    def __init__(self):
        """Initialize Airtable client."""
        self.token = os.getenv('AIRTABLE_TOKEN')
        self.base_id = os.getenv('AIRTABLE_BASE_ID')
        self.table_name = "Services"
        
        if not self.token:
            raise ValueError("AIRTABLE_TOKEN environment variable not set")
        if not self.base_id:
            raise ValueError("AIRTABLE_BASE_ID environment variable not set")
        
        self.api = Api(self.token)
        self.table = self.api.table(self.base_id, self.table_name)
        
        logger.info(f"Airtable client initialized: {self.base_id}/{self.table_name}")
    
    def get_service(self, service_id: str) -> Optional[Dict[str, Any]]:
        """
        Get Service record by ID.
        
        Args:
            service_id: Airtable record ID
            
        Returns:
            Service record fields or None if not found
        """
        try:
            record = self.table.get(service_id)
            return record['fields']
        except Exception as e:
            logger.error(f"Failed to get service {service_id}: {e}")
            return None
    
    def update_service(self, service_id: str, fields: Dict[str, Any]) -> bool:
        """
        Update Service record.
        
        Args:
            service_id: Airtable record ID
            fields: Fields to update
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.table.update(service_id, fields)
            logger.info(f"Updated service {service_id}: {list(fields.keys())}")
            return True
        except Exception as e:
            logger.error(f"Failed to update service {service_id}: {e}")
            return False
