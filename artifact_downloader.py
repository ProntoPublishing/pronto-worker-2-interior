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
            artifact_url: Public URL to manuscript.v1.json
            
        Returns:
            Parsed artifact dict
        """
        logger.info(f"Downloading artifact from {artifact_url}")
        
        try:
            response = requests.get(artifact_url, timeout=30)
            response.raise_for_status()
            
            artifact = response.json()
            
            logger.info(f"Artifact downloaded: {len(artifact.get('content', {}).get('blocks', []))} blocks")
            
            return artifact
        
        except requests.RequestException as e:
            logger.error(f"Failed to download artifact: {e}")
            raise ValueError(f"Could not download artifact from {artifact_url}: {str(e)}")
        
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse artifact JSON: {e}")
            raise ValueError(f"Invalid JSON in artifact: {str(e)}")
