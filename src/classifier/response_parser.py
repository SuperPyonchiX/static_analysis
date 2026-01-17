"""LLM分類結果のレスポンスパーサー。"""

from typing import Optional
import logging

from ..models.classification import ClassificationResult, ClassificationType
from .llm_client import ClassificationResponse, ClassificationTypeEnum

logger = logging.getLogger(__name__)


class ResponseParser:
    """LLMレスポンスをClassificationResultオブジェクトにパースする。"""

    # LLM列挙から内部列挙へのマッピング
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
        """LLMレスポンスをClassificationResultにパースする。

        Args:
            response: LLMレスポンスオブジェクト
            finding_id: 分類対象の指摘ID
            phase: 分類フェーズ（1または2）

        Returns:
            ClassificationResultオブジェクト
        """
        # 分類タイプをマッピング
        classification_type = self.TYPE_MAPPING.get(
            response.classification,
            ClassificationType.UNDETERMINED
        )

        # 統合された理由を構築
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
        """レスポンスから統合された理由文字列を構築する。

        Args:
            response: LLMレスポンスオブジェクト

        Returns:
            統合された理由文字列
        """
        parts = []

        # メインの理由
        if response.reason:
            parts.append(response.reason)

        # メインの理由と異なる場合はルール分析を追加
        if response.rule_analysis and response.rule_analysis != response.reason:
            # 長すぎる場合は切り詰める
            rule_text = response.rule_analysis
            if len(rule_text) > 200:
                rule_text = rule_text[:197] + "..."
            parts.append(f"[ルール観点] {rule_text}")

        # 異なる場合はコード分析を追加
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
        """分類失敗時のエラー結果を作成する。

        Args:
            finding_id: 指摘のID
            error_message: エラーメッセージ
            phase: 分類フェーズ

        Returns:
            UNDETERMINED分類のClassificationResult
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
        """スキップされた指摘の結果を作成する。

        Args:
            finding_id: 指摘のID
            skip_reason: スキップの理由
            phase: 分類フェーズ

        Returns:
            UNDETERMINED分類のClassificationResult
        """
        return ClassificationResult(
            finding_id=finding_id,
            classification=ClassificationType.UNDETERMINED,
            confidence=0.0,
            reason=f"スキップ: {skip_reason}",
            phase=phase
        )
