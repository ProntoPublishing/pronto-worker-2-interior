"""
Warning Handler - FAIL/DEGRADE/PROCEED Logic
=============================================

Evaluates warnings from manuscript.v1.json and decides processing strategy.

Based on Pronto Artifacts Registry PROCESSING_POLICY.md

Author: Pronto Publishing
Version: 1.0.0
"""

import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ProcessingDecision:
    """Decision on how to process manuscript based on warnings."""
    action: str  # "FAIL", "DEGRADE", or "PROCEED"
    reason: Optional[str] = None
    degradations: Optional[List[str]] = None


class WarningHandler:
    """Evaluates warnings and decides processing strategy."""
    
    def __init__(self):
        """Initialize with processing policy rules."""
        # FAIL rules: Cannot process at all
        self.fail_rules = {
            'DETECTED_IMAGES': 'Images not supported in MVP',
            'DETECTED_TABLES': 'Tables not supported in MVP',
        }
        
        # DEGRADE rules: Can process with fallback rendering
        self.degrade_rules = {
            'DETECTED_FOOTNOTES': 'Footnotes rendered inline',
            'POEM_LIKE_BLOCKS': 'Poetry rendered as blockquotes',
            'UNICODE_RISK': 'Non-standard characters may render incorrectly',
            'EXCESSIVE_WHITESPACE': 'Extra spacing normalized',
            'CENTERED_TEXT_BLOCKS': 'Centered text rendered left-aligned',
            'OCR_ARTIFACTS': 'OCR errors may affect quality',
            'FORMATTING_INCONSISTENCY': 'Inconsistent formatting normalized',
        }
        
        # PROCEED rules: Can process normally (just log)
        self.proceed_rules = {
            'LOW_CHAPTER_CONFIDENCE': 'Chapter detection uncertain but proceeding',
        }
        
        # Thresholds for multiple warnings
        self.max_degrade_warnings = 5  # If more than 5 DEGRADE warnings, fail
    
    def evaluate(self, warnings: List[Dict[str, Any]]) -> ProcessingDecision:
        """
        Evaluate warnings and decide processing strategy.
        
        Args:
            warnings: List of warnings from manuscript artifact
            
        Returns:
            ProcessingDecision with action and reason
        """
        if not warnings:
            logger.info("No warnings detected - proceeding normally")
            return ProcessingDecision(action="PROCEED")
        
        logger.info(f"Evaluating {len(warnings)} warnings")
        
        # Check for FAIL conditions
        fail_warnings = []
        for warning in warnings:
            code = warning['code']
            if code in self.fail_rules:
                fail_warnings.append(code)
        
        if fail_warnings:
            reason = f"Cannot process: {', '.join([self.fail_rules[code] for code in fail_warnings])}"
            logger.error(f"FAIL decision: {reason}")
            return ProcessingDecision(action="FAIL", reason=reason)
        
        # Check for DEGRADE conditions
        degrade_warnings = []
        degradations = []
        
        for warning in warnings:
            code = warning['code']
            if code in self.degrade_rules:
                degrade_warnings.append(code)
                degradations.append(self.degrade_rules[code])
        
        # If too many DEGRADE warnings, fail
        if len(degrade_warnings) > self.max_degrade_warnings:
            reason = f"Too many edge cases ({len(degrade_warnings)} warnings) - quality would be poor"
            logger.error(f"FAIL decision: {reason}")
            return ProcessingDecision(action="FAIL", reason=reason)
        
        if degrade_warnings:
            logger.warning(f"DEGRADE decision: {len(degrade_warnings)} warnings")
            for degradation in degradations:
                logger.warning(f"  - {degradation}")
            return ProcessingDecision(
                action="DEGRADE",
                reason=f"{len(degrade_warnings)} edge cases detected",
                degradations=degradations
            )
        
        # Check for PROCEED conditions (informational only)
        proceed_warnings = []
        for warning in warnings:
            code = warning['code']
            if code in self.proceed_rules:
                proceed_warnings.append(code)
                logger.info(f"  - {self.proceed_rules[code]}")
        
        if proceed_warnings:
            logger.info(f"PROCEED decision with {len(proceed_warnings)} informational warnings")
            return ProcessingDecision(action="PROCEED")
        
        # Unknown warnings - log and proceed
        unknown_warnings = [w['code'] for w in warnings if w['code'] not in self.fail_rules 
                          and w['code'] not in self.degrade_rules 
                          and w['code'] not in self.proceed_rules]
        
        if unknown_warnings:
            logger.warning(f"Unknown warning codes: {unknown_warnings} - proceeding anyway")
        
        return ProcessingDecision(action="PROCEED")
    
    def get_policy_summary(self) -> Dict[str, Any]:
        """Get summary of processing policy rules."""
        return {
            'fail_rules': self.fail_rules,
            'degrade_rules': self.degrade_rules,
            'proceed_rules': self.proceed_rules,
            'max_degrade_warnings': self.max_degrade_warnings
        }
