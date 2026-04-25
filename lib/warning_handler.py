"""
Warning Handler - FAIL/DEGRADE/PROCEED Logic
=============================================

Evaluates warnings from a manuscript artifact and decides processing
strategy. Reads BOTH v1.0 (legacy `code` field) and v2.0 (`rule`
field) warning shapes via _warning_code().

Contract drift note (2026-04-25): v2.0's warning vocabulary is
Doc 22 rule IDs (V-001 chapter gap, V-002 heading inconsistency,
V-003 space-loss, V-004 tracked-changes residue, H-001 intake-vs-
manuscript divergence). None of those land in the v1.0 legacy
fail/degrade/proceed rule maps below — they all currently fall
through to PROCEED. That's correct v5 behavior: V-### / H-### are
advisory, not blocking. A proper v2.0 rule-bucket mapping
(authoritative FAIL/DEGRADE/PROCEED for V-001..V-004 and H-001) is
on the post-unblock punchlist.

Based on Pronto Artifacts Registry PROCESSING_POLICY.md.

Author: Pronto Publishing
Version: 1.0.1 (v2.0-tolerant; production unblock 2026-04-25)
"""

import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


def _warning_code(warning: Dict[str, Any]) -> Optional[str]:
    """Extract a warning's identifier across schema versions.

    v2.0 warnings (manuscript.v2.0 schema) carry `rule` — e.g.,
    "V-001", "V-003", "H-001". v1.0 legacy warnings carry `code` —
    e.g., "DETECTED_IMAGES", "OCR_ARTIFACTS". A malformed warning
    with neither field returns None and is skipped by the caller —
    the rest of the artifact's warnings still get evaluated, and the
    misshapen entry is logged once at the call site.
    """
    return warning.get("rule") or warning.get("code")


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
        
        # Check for FAIL conditions. Skip malformed warnings (no rule/
        # code field at all) — log the count, don't crash. v2.0 rule
        # IDs (V-###, H-###) won't match self.fail_rules; they're
        # advisory and fall through to PROCEED. Same applies to the
        # DEGRADE / PROCEED loops below.
        malformed_count = 0
        fail_warnings = []
        for warning in warnings:
            code = _warning_code(warning)
            if code is None:
                malformed_count += 1
                continue
            if code in self.fail_rules:
                fail_warnings.append(code)
        if malformed_count:
            logger.warning(
                f"{malformed_count} warning(s) carried neither 'rule' nor "
                f"'code'; skipped (artifact may not match v1.0 or v2.0 "
                f"warning schema)."
            )
        
        if fail_warnings:
            reason = f"Cannot process: {', '.join([self.fail_rules[code] for code in fail_warnings])}"
            logger.error(f"FAIL decision: {reason}")
            return ProcessingDecision(action="FAIL", reason=reason)
        
        # Check for DEGRADE conditions
        degrade_warnings = []
        degradations = []

        for warning in warnings:
            code = _warning_code(warning)
            if code is None:
                continue
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
            code = _warning_code(warning)
            if code is None:
                continue
            if code in self.proceed_rules:
                proceed_warnings.append(code)
                logger.info(f"  - {self.proceed_rules[code]}")
        
        if proceed_warnings:
            logger.info(f"PROCEED decision with {len(proceed_warnings)} informational warnings")
            return ProcessingDecision(action="PROCEED")
        
        # Unknown warnings - log and proceed. With v2.0 artifacts, the
        # entire V-001..V-004 / H-001 set lands here today (no rule
        # entries in any of the three legacy maps). That's correct
        # interim behavior — the proper v2.0 rule-bucket mapping is on
        # the post-unblock punchlist.
        unknown_warnings = []
        for w in warnings:
            code = _warning_code(w)
            if code is None:
                continue
            if (code not in self.fail_rules
                    and code not in self.degrade_rules
                    and code not in self.proceed_rules):
                unknown_warnings.append(code)

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
