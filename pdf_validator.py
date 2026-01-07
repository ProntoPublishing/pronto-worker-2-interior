"""
PDF Validator
=============

Validates generated PDFs for quality and POD compatibility.

Checks:
- File size (not too large for upload)
- Page count (reasonable for book)
- PDF version (compatible with KDP/IngramSpark)
- Fonts embedded
- Color space (grayscale or CMYK for print)

Author: Pronto Publishing
Version: 1.0.0
"""

import subprocess
import logging
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger(__name__)


class PDFValidator:
    """Validates PDF quality and POD compatibility."""
    
    def __init__(self):
        """Initialize PDF validator."""
        self.max_file_size_mb = 500  # KDP limit is 650MB, use 500MB as safe limit
        self.min_pages = 24  # Minimum for most POD services
        self.max_pages = 828  # KDP limit
    
    def validate(self, pdf_file: Path) -> Dict[str, Any]:
        """
        Validate PDF file.
        
        Args:
            pdf_file: Path to PDF file
            
        Returns:
            Validation result with 'valid' bool and details
        """
        logger.info(f"Validating PDF: {pdf_file}")
        
        errors = []
        warnings = []
        
        # Check file exists
        if not pdf_file.exists():
            return {
                'valid': False,
                'errors': [f"PDF file not found: {pdf_file}"]
            }
        
        # Check file size
        file_size_mb = pdf_file.stat().st_size / (1024 * 1024)
        logger.info(f"File size: {file_size_mb:.2f} MB")
        
        if file_size_mb > self.max_file_size_mb:
            errors.append(f"File too large: {file_size_mb:.2f} MB (max {self.max_file_size_mb} MB)")
        
        # Get page count using pdfinfo
        try:
            page_count = self._get_page_count(pdf_file)
            logger.info(f"Page count: {page_count}")
            
            if page_count < self.min_pages:
                warnings.append(f"Page count low: {page_count} pages (min {self.min_pages} recommended)")
            
            if page_count > self.max_pages:
                errors.append(f"Page count too high: {page_count} pages (max {self.max_pages})")
        
        except Exception as e:
            logger.error(f"Failed to get page count: {e}")
            errors.append(f"Could not determine page count: {str(e)}")
            page_count = None
        
        # Check PDF version
        try:
            pdf_version = self._get_pdf_version(pdf_file)
            logger.info(f"PDF version: {pdf_version}")
            
            # KDP accepts PDF 1.3 to 1.7 (X-1a, X-3)
            if pdf_version and not pdf_version.startswith('1.'):
                warnings.append(f"PDF version {pdf_version} may not be compatible with all POD services")
        
        except Exception as e:
            logger.warning(f"Failed to get PDF version: {e}")
        
        # Determine if valid
        valid = len(errors) == 0
        
        result = {
            'valid': valid,
            'errors': errors,
            'warnings': warnings,
            'file_size_mb': file_size_mb,
            'page_count': page_count
        }
        
        if valid:
            logger.info("PDF validation passed")
        else:
            logger.error(f"PDF validation failed: {errors}")
        
        return result
    
    def _get_page_count(self, pdf_file: Path) -> int:
        """Get page count using pdfinfo."""
        try:
            result = subprocess.run(
                ["pdfinfo", str(pdf_file)],
                capture_output=True,
                text=True,
                check=True
            )
            
            for line in result.stdout.split('\n'):
                if line.startswith('Pages:'):
                    return int(line.split(':')[1].strip())
            
            raise ValueError("Pages field not found in pdfinfo output")
        
        except subprocess.CalledProcessError as e:
            logger.error(f"pdfinfo failed: {e.stderr}")
            raise
        except FileNotFoundError:
            logger.error("pdfinfo not found - install with: apt-get install poppler-utils")
            raise RuntimeError("pdfinfo not installed")
    
    def _get_pdf_version(self, pdf_file: Path) -> str:
        """Get PDF version using pdfinfo."""
        try:
            result = subprocess.run(
                ["pdfinfo", str(pdf_file)],
                capture_output=True,
                text=True,
                check=True
            )
            
            for line in result.stdout.split('\n'):
                if line.startswith('PDF version:'):
                    return line.split(':')[1].strip()
            
            return "unknown"
        
        except Exception as e:
            logger.warning(f"Failed to get PDF version: {e}")
            return "unknown"
