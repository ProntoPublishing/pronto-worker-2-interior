"""
Pronto Worker 2 - Interior Formatting Processor v1.1.0 (Canon-Compliant)
=========================================================================

Converts manuscript.v1.json artifacts to formatted interior PDFs.

CANONICAL CHANGES IN v1.1.0:
- Reads manuscript artifact via deterministic dependency lookup (by Service Type)
- Reads formatting parameters from linked Book Metadata table
- Writes to generic Artifact URL and Artifact Key fields
- Uses canonical Status values: Processing → Complete/Failed
- Uses canonical Error Log field (not Error Message)
- Implements proper status lifecycle: claim → process → complete
- Ignores non-canonical Statuses (plural) field

Architecture:
1. Claim service (Status → Processing)
2. Find Worker 1 dependency by Service Type
3. Download manuscript.v1.json from dependency's Artifact URL
4. Get formatting parameters from linked Book Metadata
5. Validate artifact schema
6. Check warnings (FAIL/DEGRADE/PROCEED)
7. Convert blocks to LaTeX
8. Generate PDF with Pandoc + XeLaTeX
9. Validate PDF quality
10. Upload to R2
11. Update Airtable Service record (Status → Complete)

Author: Pronto Publishing
Version: 1.1.0
Date: 2026-01-05
"""

import os
import sys
import json
import logging
import subprocess
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from uuid import uuid4

# Add lib to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'lib'))

from pronto_r2_client import ProntoR2Client
from artifact_downloader import ArtifactDownloader
from artifact_validator import validate_artifact
from warning_handler import WarningHandler, ProcessingDecision
from blocks_to_latex import BlocksToLatexConverter
from pdf_generator import PDFGenerator
from pdf_validator import PDFValidator
from airtable_client import AirtableClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class InteriorProcessor:
    """Main Worker 2 processor."""
    
    def __init__(self):
        """Initialize processor with all dependencies."""
        self.worker_name = "worker_2_interior_formatter"
        self.worker_version = "1.1.0"
        
        # Initialize clients
        self.r2_client = ProntoR2Client(
            account_id=os.getenv('R2_ACCOUNT_ID'),
            access_key_id=os.getenv('R2_ACCESS_KEY_ID'),
            secret_access_key=os.getenv('R2_SECRET_ACCESS_KEY'),
            bucket_name=os.getenv('R2_BUCKET_NAME', 'pronto-artifacts'),
            public_base_url=os.getenv('R2_PUBLIC_BASE_URL')
        )
        self.airtable_client = AirtableClient()
        self.artifact_downloader = ArtifactDownloader(self.r2_client)
        
        # Initialize processors
        self.warning_handler = WarningHandler()
        self.latex_converter = BlocksToLatexConverter()
        self.pdf_generator = PDFGenerator()
        self.pdf_validator = PDFValidator()
        
        # Work directory
        self.work_dir = Path("/tmp/worker_2")
        self.work_dir.mkdir(exist_ok=True)
    
    def process_service(self, service_id: str) -> Dict[str, Any]:
        """
        Process a Service record: manuscript.v1.json → interior.pdf
        
        Args:
            service_id: Airtable Service record ID
            
        Returns:
            Processing result with status, URLs, metadata
        """
        run_id = str(uuid4())
        started_at = datetime.now(timezone.utc)
        
        logger.info(f"[{run_id}] Starting Worker 2 for service {service_id}")
        
        try:
            # Step 1: Get Service record from Airtable
            service = self.airtable_client.get_service(service_id)
            if not service:
                raise ValueError(f"Service {service_id} not found")
            
            # Step 2: CANONICAL - Claim the service
            self._claim_service(service_id)
            
            # Step 3: CANONICAL - Find manuscript artifact via deterministic dependency lookup
            manuscript_artifact_url = self._find_manuscript_artifact(service)
            if not manuscript_artifact_url:
                raise ValueError("Could not find manuscript artifact from Worker 1 dependency")
            
            logger.info(f"[{run_id}] Found manuscript artifact: {manuscript_artifact_url}")
            
            # Step 4: CANONICAL - Get formatting parameters from linked Book Metadata
            params = self._get_formatting_parameters(service)
            logger.info(f"[{run_id}] Formatting parameters: {params}")
            
            # Step 5: Download and validate manuscript artifact
            artifact = self.artifact_downloader.download(manuscript_artifact_url)
            
            validation_result = validate_artifact(
                artifact,
                artifact_type="manuscript",
                schema_version="1.0"
            )
            
            if not validation_result['valid']:
                raise ValueError(f"Invalid artifact: {validation_result['errors']}")
            
            logger.info(f"[{run_id}] Artifact validated successfully")
            
            # Step 6: Check warnings and decide processing strategy
            warnings = artifact.get('analysis', {}).get('warnings', [])
            decision = self.warning_handler.evaluate(warnings)
            
            logger.info(f"[{run_id}] Warning decision: {decision.action}")
            
            if decision.action == "FAIL":
                raise ValueError(f"Cannot process: {decision.reason}")
            
            # Step 7: Convert blocks to LaTeX
            latex_content = self.latex_converter.convert(
                blocks=artifact['content']['blocks'],
                params=params,
                degraded_mode=(decision.action == "DEGRADE")
            )
            
            # Save LaTeX to work directory
            latex_file = self.work_dir / f"{run_id}.tex"
            latex_file.write_text(latex_content, encoding='utf-8')
            logger.info(f"[{run_id}] LaTeX generated: {latex_file}")
            
            # Step 8: Generate PDF with Pandoc + XeLaTeX
            pdf_file = self.pdf_generator.generate(
                latex_file=latex_file,
                output_dir=self.work_dir,
                run_id=run_id
            )
            logger.info(f"[{run_id}] PDF generated: {pdf_file}")
            
            # Step 9: Validate PDF quality
            pdf_validation = self.pdf_validator.validate(pdf_file)
            
            if not pdf_validation['valid']:
                raise ValueError(f"PDF validation failed: {pdf_validation['errors']}")
            
            logger.info(f"[{run_id}] PDF validated: {pdf_validation['page_count']} pages")
            
            # Step 10: Upload PDF to R2
            pdf_key = f"services/{service_id}/interior.pdf"
            upload_result = self.r2_client.upload_file(
                file_path=str(pdf_file),
                object_key=pdf_key,
                content_type="application/pdf"
            )
            
            pdf_url = upload_result['public_url']
            logger.info(f"[{run_id}] PDF uploaded: {pdf_url}")
            
            # Step 11: CANONICAL - Update Airtable with Complete status
            completed_at = datetime.now(timezone.utc)
            duration = (completed_at - started_at).total_seconds()
            
            self._complete_service(
                service_id=service_id,
                pdf_url=pdf_url,
                pdf_key=pdf_key,
                page_count=pdf_validation['page_count'],
                duration=duration,
                degradations=decision.degradations
            )
            
            logger.info(f"[{run_id}] Service updated in Airtable")
            
            # Step 12: Clean up work files
            latex_file.unlink(missing_ok=True)
            pdf_file.unlink(missing_ok=True)
            
            return {
                'success': True,
                'service_id': service_id,
                'pdf_url': pdf_url,
                'page_count': pdf_validation['page_count'],
                'duration_seconds': duration,
                'warnings': decision.degradations,
                'run_id': run_id
            }
            
        except Exception as e:
            logger.error(f"[{run_id}] Processing failed: {str(e)}", exc_info=True)
            
            # CANONICAL - Update Airtable with Failed status
            self._fail_service(service_id, str(e))
            
            return {
                'success': False,
                'service_id': service_id,
                'error': str(e),
                'run_id': run_id
            }
    
    def _find_manuscript_artifact(self, service: Dict[str, Any]) -> Optional[str]:
        """
        CANONICAL: Find the manuscript artifact URL via deterministic dependency lookup.
        
        Searches through the service's dependencies to find the one with
        Service Type = "Manuscript Processing" and returns its Artifact URL.
        
        Args:
            service: The current Service record
            
        Returns:
            URL of the manuscript.v1.json artifact, or None if not found
        """
        dependencies = service.get('Dependencies', [])
        
        if not dependencies:
            logger.error("No dependencies found for this Service")
            return None
        
        logger.info(f"Searching {len(dependencies)} dependencies for Manuscript Processing service")
        
        # Iterate through dependencies to find the Worker 1 service
        for dep_id in dependencies:
            dep_service = self.airtable_client.get_service(dep_id)
            
            if not dep_service:
                logger.warning(f"Could not fetch dependency {dep_id}")
                continue
            
            # Get the Service Type (this is a linked record, so we get the ID)
            service_type_links = dep_service.get('Service Type', [])
            
            if not service_type_links:
                continue
            
            # Fetch the Service Type record to get its name
            service_type_id = service_type_links[0]
            service_type = self.airtable_client.get_service_type(service_type_id)
            
            if not service_type:
                continue
            
            service_type_name = service_type.get('Service Name', '')
            
            logger.info(f"Checking dependency {dep_id}: Service Type = {service_type_name}")
            
            # CANONICAL: Match by Service Type name
            if service_type_name == "Manuscript Processing":
                artifact_url = dep_service.get('Artifact URL')
                
                if artifact_url:
                    logger.info(f"Found manuscript artifact from dependency {dep_id}")
                    return artifact_url
                else:
                    logger.warning(f"Dependency {dep_id} is Manuscript Processing but has no Artifact URL")
        
        logger.error("No Manuscript Processing dependency found with Artifact URL")
        return None
    
    def _get_formatting_parameters(self, service: Dict[str, Any]) -> Dict[str, Any]:
        """
        CANONICAL: Get formatting parameters from linked Book Metadata table.
        
        Follows the link chain: Service → Project → Book Metadata
        
        Args:
            service: The current Service record
            
        Returns:
            Dict of formatting parameters with defaults
        """
        # Default parameters (used if lookups fail)
        defaults = {
            'trim_size': '6x9',
            'font': 'Garamond',
            'chapter_style': 'numbered',
            'genre': 'fiction',
            'author_name': 'Author',
            'book_title': 'Untitled'
        }
        
        try:
            # Get linked Project
            project_links = service.get('Project', [])
            
            if not project_links:
                logger.warning("No Project linked to Service, using defaults")
                return defaults
            
            project_id = project_links[0]
            project = self.airtable_client.get_project(project_id)
            
            if not project:
                logger.warning(f"Could not fetch Project {project_id}, using defaults")
                return defaults
            
            # Get linked Book Metadata
            metadata_links = project.get('Book Metadata', [])
            
            if not metadata_links:
                logger.warning("No Book Metadata linked to Project, using defaults")
                return defaults
            
            metadata_id = metadata_links[0]
            metadata = self.airtable_client.get_book_metadata(metadata_id)
            
            if not metadata:
                logger.warning(f"Could not fetch Book Metadata {metadata_id}, using defaults")
                return defaults
            
            # Extract parameters from Book Metadata
            params = {
                'trim_size': metadata.get('Trim Size', defaults['trim_size']),
                'font': defaults['font'],  # Font not in Book Metadata yet
                'chapter_style': defaults['chapter_style'],  # Not in Book Metadata yet
                'genre': defaults['genre'],  # Not in Book Metadata yet
                'author_name': metadata.get('Author Name', defaults['author_name']),
                'book_title': metadata.get('Book Title', defaults['book_title'])
            }
            
            logger.info("Successfully retrieved formatting parameters from Book Metadata")
            return params
            
        except Exception as e:
            logger.error(f"Error getting formatting parameters: {e}, using defaults")
            return defaults
    
    def _claim_service(self, service_id: str):
        """
        CANONICAL: Claim the service by setting Status to Processing.
        """
        fields = {
            # NOTE: Only use 'Status' (singular), never 'Statuses' (plural)
            'Status': 'Processing',
            'Started At': datetime.now(timezone.utc).isoformat(),
            'Worker Version': self.worker_version
        }
        
        self.airtable_client.update_service(service_id, fields)
        logger.info(f"Claimed service {service_id}: Status → Processing")
    
    def _complete_service(
        self,
        service_id: str,
        pdf_url: str,
        pdf_key: str,
        page_count: int,
        duration: float,
        degradations: Optional[List[str]]
    ):
        """
        CANONICAL: Mark service as Complete and store outputs.
        Uses generic Artifact URL and Artifact Key fields.
        """
        fields = {
            # NOTE: Only use 'Status' (singular), never 'Statuses' (plural)
            'Status': 'Complete',
            'Finished At': datetime.now(timezone.utc).isoformat(),
            # CANONICAL: Write to generic artifact fields
            'Artifact URL': pdf_url,
            'Artifact Key': pdf_key,
            'Artifact Type': 'interior_pdf'
        }
        
        # Store additional metadata in Operator Notes
        metadata = {
            'page_count': page_count,
            'duration_seconds': duration,
            'degradations': degradations
        }
        fields['Operator Notes'] = f"Interior PDF: {json.dumps(metadata, indent=2)}"
        
        self.airtable_client.update_service(service_id, fields)
        logger.info(f"Completed service {service_id}: Status → Complete")
    
    def _fail_service(self, service_id: str, error_message: str):
        """
        CANONICAL: Mark service as Failed and store error details.
        Uses canonical Error Log field (not Error Message).
        """
        fields = {
            # NOTE: Only use 'Status' (singular), never 'Statuses' (plural)
            'Status': 'Failed',
            'Finished At': datetime.now(timezone.utc).isoformat(),
            # CANONICAL: Use Error Log field
            'Error Log': error_message
        }
        
        self.airtable_client.update_service(service_id, fields)
        logger.info(f"Failed service {service_id}: Status → Failed")


def main():
    """CLI entry point."""
    if len(sys.argv) < 2:
        print("Usage: python pronto_worker_2_v1.1.0_canonical.py <service_id>")
        sys.exit(1)
    
    service_id = sys.argv[1]
    
    # Validate environment
    required_vars = [
        'R2_ACCOUNT_ID',
        'R2_ACCESS_KEY_ID',
        'R2_SECRET_ACCESS_KEY',
        'R2_PUBLIC_BASE_URL'
    ]
    
    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        logger.error(f"Missing required environment variables: {', '.join(missing)}")
        sys.exit(1)
    
    processor = InteriorProcessor()
    result = processor.process_service(service_id)
    
    print(json.dumps(result, indent=2))
    
    sys.exit(0 if result['success'] else 1)


if __name__ == '__main__':
    main()
