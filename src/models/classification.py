"""Classification result model."""

from dataclasses import dataclass
from typing import Optional
from enum import Enum


class ClassificationType(Enum):
    """Classification type for static analysis findings."""
    FALSE_POSITIVE = "誤検知"    # False positive - tool error
    DEVIATION = "逸脱"          # Intentional deviation with justification
    FIX_REQUIRED = "修正"       # Actual issue requiring fix
    UNDETERMINED = "判定不可"   # Could not determine


@dataclass
class ClassificationResult:
    """Result of classifying a finding."""
    finding_id: str
    classification: ClassificationType
    confidence: float  # 0.0 - 1.0
    reason: str
    phase: int  # 1 or 2

    # Optional detailed information
    rule_explanation: Optional[str] = None
    code_context_summary: Optional[str] = None

    def is_high_confidence(self, threshold: float = 0.8) -> bool:
        """Check if confidence is above threshold.

        Args:
            threshold: Confidence threshold (default: 0.8)

        Returns:
            True if confidence >= threshold
        """
        return self.confidence >= threshold

    def to_excel_dict(self) -> dict:
        """Convert to dictionary for Excel output.

        Returns:
            Dictionary with Excel column values
        """
        return {
            "分類": self.classification.value,
            "分類理由": self.reason,
            "確信度": f"{self.confidence:.0%}",
            "判定フェーズ": self.phase
        }

    def __str__(self) -> str:
        return (
            f"[{self.finding_id}] {self.classification.value} "
            f"(confidence: {self.confidence:.0%}, phase: {self.phase})"
        )
