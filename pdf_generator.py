"""
PDF Generator - Pandoc + XeLaTeX
=================================

Generates print-ready PDFs from LaTeX files using Pandoc and XeLaTeX.

Author: Pronto Publishing
Version: 1.0.0
"""

import subprocess
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class PDFGenerator:
    """Generates PDFs using Pandoc + XeLaTeX."""
    
    def __init__(self):
        """Initialize PDF generator."""
        self.pandoc_cmd = "pandoc"
        self.xelatex_cmd = "xelatex"
        
        # Check if Pandoc is installed
        try:
            subprocess.run([self.pandoc_cmd, "--version"], 
                         capture_output=True, check=True)
            logger.info("Pandoc found")
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.error("Pandoc not found - install with: apt-get install pandoc")
            raise RuntimeError("Pandoc not installed")
        
        # Check if XeLaTeX is installed
        try:
            subprocess.run([self.xelatex_cmd, "--version"], 
                         capture_output=True, check=True)
            logger.info("XeLaTeX found")
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.error("XeLaTeX not found - install with: apt-get install texlive-xetex")
            raise RuntimeError("XeLaTeX not installed")
    
    def generate(
        self,
        latex_file: Path,
        output_dir: Path,
        run_id: str
    ) -> Path:
        """
        Generate PDF from LaTeX file.
        
        Args:
            latex_file: Path to .tex file
            output_dir: Directory for output files
            run_id: Unique run identifier
            
        Returns:
            Path to generated PDF
        """
        logger.info(f"Generating PDF from {latex_file}")
        
        # Output PDF path
        pdf_file = output_dir / f"{run_id}.pdf"
        
        # Run XeLaTeX directly (Pandoc not needed for .tex → .pdf)
        # We need to run XeLaTeX twice for proper page numbers and TOC
        
        for run_num in [1, 2]:
            logger.info(f"Running XeLaTeX (pass {run_num}/2)")
            
            result = subprocess.run(
                [
                    self.xelatex_cmd,
                    "-interaction=nonstopmode",  # Don't stop on errors
                    "-output-directory", str(output_dir),
                    "-jobname", run_id,  # Output filename without extension
                    str(latex_file)
                ],
                capture_output=True,
                text=True,
                cwd=str(output_dir)
            )
            
            if result.returncode != 0:
                logger.error(f"XeLaTeX failed (pass {run_num}):")
                logger.error(result.stdout)
                logger.error(result.stderr)
                raise RuntimeError(f"XeLaTeX compilation failed: {result.stderr}")
            
            logger.info(f"XeLaTeX pass {run_num} completed")
        
        # Check if PDF was created
        if not pdf_file.exists():
            raise RuntimeError(f"PDF not created: {pdf_file}")
        
        logger.info(f"PDF generated: {pdf_file} ({pdf_file.stat().st_size} bytes)")
        
        # Clean up auxiliary files
        self._cleanup_aux_files(output_dir, run_id)
        
        return pdf_file
    
    def _cleanup_aux_files(self, output_dir: Path, run_id: str):
        """Clean up LaTeX auxiliary files."""
        aux_extensions = ['.aux', '.log', '.out', '.toc']
        
        for ext in aux_extensions:
            aux_file = output_dir / f"{run_id}{ext}"
            if aux_file.exists():
                aux_file.unlink()
                logger.debug(f"Cleaned up: {aux_file}")
