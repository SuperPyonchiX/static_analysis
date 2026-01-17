"""Response parser for LLM classification results."""

from typing import Optional
import logging

from ..models.classification import ClassificationResult, ClassificationType
from .llm_client import ClassificationResponse, ClassificationTypeEnum

logger = logging.getLogger(__name__)


class ResponseParser:
    """Parse LLM responses into ClassificationResult objects."""

    # Mapping from LLM enum to internal enum
    TYPE_MAPPING = {
        ClassificationTypeEnum.FALSE_POSITIVE: ClassificationType.FALSE_POSITIVE,
        ClassificationTypeEnum.DEVIATION: ClassificationType.DEVIATION,
        ClassificationTypeEnum.FIX_REQUIRED: ClassificationType.FIX_REQUIRED,
        ClassificationTypeEnum.UNDETERMINED: ClassificationType.UNDETERMINED,
    }

    def parse(
        self,
        response: ClassificationResponse,
        finding_id: str,
        phase: int
    ) -> ClassificationResult:
        """Parse an LLM response into a ClassificationResult.

        Args:
            response: LLM response object
            finding_id: ID of the finding being classified
            phase: Classification phase (1 or 2)

        Returns:
            ClassificationResult object
        """
        # Map classification type
        classification_type = self.TYPE_MAPPING.get(
            response.classification,
            ClassificationType.UNDETERMINED
        )

        # Build combined reason
        reason = self._build_reason(response)

        return ClassificationResult(
            finding_id=finding_id,
            classification=classification_type,
            confidence=response.confidence,
            reason=reason,
            phase=phase,
            rule_explanation=response.rule_analysis,
            code_context_summary=response.code_analysis
        )

    def _build_reason(self, response: ClassificationResponse) -> str:
        """Build a combined reason string from the response.

        Args:
            response: LLM response object

        Returns:
            Combined reason string
        """
        parts = []

        # Main reason
        if response.reason:
            parts.append(response.reason)

        # Add rule analysis if different from main reason
        if response.rule_analysis and response.rule_analysis != response.reason:
            # Truncate if too long
            rule_text = response.rule_analysis
            if len(rule_text) > 200:
                rule_text = rule_text[:197] + "..."
            parts.append(f"[ルール観点] {rule_text}")

        # Add code analysis if different
        if response.code_analysis and response.code_analysis != response.reason:
            code_text = response.code_analysis
            if len(code_text) > 200:
                code_text = code_text[:197] + "..."
            parts.append(f"[コード観点] {code_text}")

        return " | ".join(parts) if parts else "理由なし"

    def create_error_result(
        self,
        finding_id: str,
        error_message: str,
        phase: int
    ) -> ClassificationResult:
        """Create an error result for failed classification.

        Args:
            finding_id: ID of the finding
            error_message: Error message
            phase: Classification phase

        Returns:
            ClassificationResult with UNDETERMINED classification
        """
        return ClassificationResult(
            finding_id=finding_id,
            classification=ClassificationType.UNDETERMINED,
            confidence=0.0,
            reason=f"判定エラー: {error_message}",
            phase=phase
        )

    def create_skip_result(
        self,
        finding_id: str,
        skip_reason: str,
        phase: int
    ) -> ClassificationResult:
        """Create a result for skipped findings.

        Args:
            finding_id: ID of the finding
            skip_reason: Reason for skipping
            phase: Classification phase

        Returns:
            ClassificationResult with UNDETERMINED classification
        """
        return ClassificationResult(
            finding_id=finding_id,
            classification=ClassificationType.UNDETERMINED,
            confidence=0.0,
            reason=f"スキップ: {skip_reason}",
            phase=phase
        )
