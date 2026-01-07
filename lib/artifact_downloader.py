"""
Artifact Downloader
===================

Downloads and parses manuscript.v1.json artifacts from R2.

Author: Pronto Publishing
Version: 1.0.0
"""

import json
import logging
import requests
from typing import Dict, Any

logger = logging.getLogger(__name__)


class ArtifactDownloader:
    """Downloads artifacts from R2."""
    
    def __init__(self, r2_client):
        """
        Initialize downloader.
        
        Args:
            r2_client: R2Client instance (not used for public URLs, but kept for consistency)
        """
        self.r2_client = r2_client
    
    def download(self, artifact_url: str) -> Dict[str, Any]:
        """
        Download and parse artifact from URL.
        
        Args:
            artifact_url: Public URL to manuscript.v1.json (or R2 key)
            
        Returns:
            Parsed artifact dict
        """
        logger.info(f"Downloading artifact from {artifact_url}")
        
        try:
            # Extract the R2 key from the URL if it's a full URL
            # URL format: https://pub-xxxxx.r2.dev/services/recXXX/manuscript.v1.json
            # Key format: services/recXXX/manuscript.v1.json
            if artifact_url.startswith('http'):
                # Extract key from URL (everything after the domain)
                key = artifact_url.split('.dev/')[-1]
                logger.info(f"Extracted R2 key: {key}")
            else:
                key = artifact_url
            
            # Download using R2 client with credentials
            artifact_json = self.r2_client.download_json(key)
            
            logger.info(f"Artifact downloaded: {len(artifact_json.get('content', {}).get('blocks', []))} blocks")
            
            return artifact_json
        
        except Exception as e:
            logger.error(f"Failed to download artifact: {e}")
            raise ValueError(f"Could not download artifact from {artifact_url}: {str(e)}")
