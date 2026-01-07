"""
Artifact Validator - Worker 2 Wrapper
======================================

Simplified wrapper around artifact_validate.py for Worker 2 usage.

Author: Pronto Publishing
Version: 1.0.0
"""

import logging
from typing import Dict, Any

from artifact_validate import validate_artifact as _validate_artifact

logger = logging.getLogger(__name__)


def validate_artifact(
    artifact: Dict[str, Any],
    artifact_type: str,
    schema_version: str
) -> Dict[str, Any]:
    """
    Validate artifact against schema.
    
    Args:
        artifact: Artifact data to validate
        artifact_type: Type of artifact (e.g., "manuscript")
        schema_version: Schema version (e.g., "1.0")
        
    Returns:
        Dict with 'valid' (bool) and 'errors' (list) keys
    """
    try:
        result = _validate_artifact(artifact, artifact_type, schema_version)
        
        if result['valid']:
            logger.info(f"Artifact validation passed: {artifact_type} v{schema_version}")
        else:
            logger.error(f"Artifact validation failed: {len(result['errors'])} errors")
            for error in result['errors']:
                logger.error(f"  - {error}")
        
        return result
        
    except Exception as e:
        logger.error(f"Validation error: {str(e)}")
        return {
            'valid': False,
            'errors': [str(e)]
        }
