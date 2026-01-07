"""
Blocks to LaTeX Converter
==========================

Converts manuscript.v1.json blocks to LaTeX markup.

Handles:
- 14 block types (front matter, chapters, paragraphs, etc.)
- 4 inline marks (italic, bold, smallcaps, code)
- Degraded mode (fallback rendering for unsupported elements)

Author: Pronto Publishing
Version: 1.0.0
"""

import re
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class BlocksToLatexConverter:
    """Converts blocks array to LaTeX markup."""
    
    def __init__(self):
        """Initialize converter with LaTeX escape rules."""
        # LaTeX special characters that need escaping
        self.latex_escapes = {
            '&': r'\&',
            '%': r'\%',
            '$': r'\$',
            '#': r'\#',
            '_': r'\_',
            '{': r'\{',
            '}': r'\}',
            '~': r'\textasciitilde{}',
            '^': r'\textasciicircum{}',
            '\\': r'\textbackslash{}',
        }
    
    def convert(
        self,
        blocks: List[Dict[str, Any]],
        params: Dict[str, Any],
        degraded_mode: bool = False
    ) -> str:
        """
        Convert blocks to LaTeX.
        
        Args:
            blocks: List of blocks from manuscript artifact
            params: Formatting parameters (trim size, font, etc.)
            degraded_mode: If True, use fallback rendering for edge cases
            
        Returns:
            Complete LaTeX document as string
        """
        logger.info(f"Converting {len(blocks)} blocks to LaTeX (degraded={degraded_mode})")
        
        # Build LaTeX document
        latex_parts = []
        
        # Add preamble (will be replaced by template)
        latex_parts.append("% PREAMBLE_PLACEHOLDER")
        latex_parts.append("")
        
        # Process blocks
        for i, block in enumerate(blocks):
            block_type = block['type']
            latex = self._convert_block(block, degraded_mode)
            
            if latex:
                latex_parts.append(latex)
                latex_parts.append("")  # Blank line between blocks
        
        return "\n".join(latex_parts)
    
    def _convert_block(self, block: Dict[str, Any], degraded: bool) -> str:
        """Convert a single block to LaTeX."""
        block_type = block['type']
        text = block.get('text', '')
        marks = block.get('marks', [])
        meta = block.get('meta', {})
        
        # Apply inline marks to text
        formatted_text = self._apply_marks(text, marks)
        
        # Convert based on block type
        if block_type == 'title_page':
            return self._convert_title_page(formatted_text, meta)
        
        elif block_type == 'front_matter_heading':
            return self._convert_front_matter_heading(formatted_text)
        
        elif block_type == 'front_matter_text':
            return formatted_text
        
        elif block_type == 'chapter_heading':
            return self._convert_chapter_heading(formatted_text, meta)
        
        elif block_type == 'paragraph':
            return formatted_text
        
        elif block_type == 'scene_break':
            return self._convert_scene_break()
        
        elif block_type == 'back_matter_heading':
            return self._convert_back_matter_heading(formatted_text)
        
        elif block_type == 'back_matter_text':
            return formatted_text
        
        elif block_type == 'blockquote':
            return self._convert_blockquote(formatted_text, degraded)
        
        elif block_type == 'list_item':
            return self._convert_list_item(formatted_text, degraded)
        
        elif block_type == 'epigraph':
            return self._convert_epigraph(formatted_text, degraded)
        
        elif block_type in ['image_placeholder', 'table_placeholder', 'footnote']:
            # These should have been caught by warning handler
            if degraded:
                return f"% UNSUPPORTED: {block_type}"
            else:
                logger.warning(f"Unexpected {block_type} in non-degraded mode")
                return ""
        
        else:
            logger.warning(f"Unknown block type: {block_type}")
            return formatted_text
    
    def _apply_marks(self, text: str, marks: List[Dict[str, Any]]) -> str:
        """
        Apply inline marks to text.
        
        Args:
            text: Plain text
            marks: List of marks with type, start, end
            
        Returns:
            Text with LaTeX markup for inline styles
        """
        if not marks:
            return self._escape_latex(text)
        
        # Sort marks by start position (reverse order for insertion)
        sorted_marks = sorted(marks, key=lambda m: m['start'], reverse=True)
        
        # Apply marks from end to start (to preserve positions)
        result = text
        for mark in sorted_marks:
            mark_type = mark['type']
            start = mark['start']
            end = mark['end']
            
            # Extract marked text
            marked_text = result[start:end]
            
            # Escape LaTeX special characters
            escaped_text = self._escape_latex(marked_text)
            
            # Wrap with LaTeX command
            if mark_type == 'italic':
                wrapped = f"\\textit{{{escaped_text}}}"
            elif mark_type == 'bold':
                wrapped = f"\\textbf{{{escaped_text}}}"
            elif mark_type == 'smallcaps':
                wrapped = f"\\textsc{{{escaped_text}}}"
            elif mark_type == 'code':
                wrapped = f"\\texttt{{{escaped_text}}}"
            else:
                wrapped = escaped_text
            
            # Replace in result
            result = result[:start] + wrapped + result[end:]
        
        # Escape remaining text (outside marks)
        # This is complex - for now, assume marks cover all special chars
        # TODO: Improve this logic
        
        return result
    
    def _escape_latex(self, text: str) -> str:
        """Escape LaTeX special characters."""
        for char, escaped in self.latex_escapes.items():
            text = text.replace(char, escaped)
        return text
    
    def _convert_title_page(self, text: str, meta: Dict[str, Any]) -> str:
        """Convert title page block."""
        # Title page is handled by template
        return "% TITLE_PAGE_PLACEHOLDER"
    
    def _convert_front_matter_heading(self, text: str) -> str:
        """Convert front matter heading (Dedication, Acknowledgments, etc.)."""
        return f"\\chapter*{{{text}}}\n\\addcontentsline{{toc}}{{chapter}}{{{text}}}"
    
    def _convert_chapter_heading(self, text: str, meta: Dict[str, Any]) -> str:
        """Convert chapter heading."""
        chapter_num = meta.get('chapter_number')
        
        if chapter_num:
            # Numbered chapter
            return f"\\chapter{{{text}}}"
        else:
            # Unnumbered chapter (prologue, epilogue, etc.)
            return f"\\chapter*{{{text}}}\n\\addcontentsline{{toc}}{{chapter}}{{{text}}}"
    
    def _convert_scene_break(self) -> str:
        """Convert scene break."""
        return "\\scenebreak"
    
    def _convert_back_matter_heading(self, text: str) -> str:
        """Convert back matter heading."""
        return f"\\chapter*{{{text}}}\n\\addcontentsline{{toc}}{{chapter}}{{{text}}}"
    
    def _convert_blockquote(self, text: str, degraded: bool) -> str:
        """Convert blockquote."""
        if degraded:
            # Fallback: render as indented paragraph
            return f"\\begin{{quote}}\n{text}\n\\end{{quote}}"
        else:
            return f"\\begin{{quotation}}\n{text}\n\\end{{quotation}}"
    
    def _convert_list_item(self, text: str, degraded: bool) -> str:
        """Convert list item."""
        if degraded:
            # Fallback: render as paragraph with bullet
            return f"• {text}"
        else:
            # Proper list (requires grouping - TODO)
            return f"\\item {text}"
    
    def _convert_epigraph(self, text: str, degraded: bool) -> str:
        """Convert epigraph."""
        if degraded:
            # Fallback: render as right-aligned italic
            return f"\\begin{{flushright}}\n\\textit{{{text}}}\n\\end{{flushright}}"
        else:
            # Proper epigraph package (TODO)
            return f"\\epigraph{{{text}}}{{}}"
