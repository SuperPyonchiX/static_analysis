"""分類結果モデル。"""

from dataclasses import dataclass
from typing import Optional
from enum import Enum


class ClassificationType(Enum):
    """静的解析指摘の分類タイプ。"""
    FALSE_POSITIVE = "誤検知"    # 誤検知 - ツールの誤判定
    DEVIATION = "逸脱"          # 意図的な逸脱（正当な理由あり）
    FIX_REQUIRED = "修正"       # 修正が必要な実際の問題
    UNDETERMINED = "判定不可"   # 判定不能


@dataclass
class ClassificationResult:
    """指摘の分類結果。"""
    finding_id: str
    classification: ClassificationType
    confidence: float  # 0.0 - 1.0
    reason: str
    phase: int  # 1 or 2

    # Optional detailed information
    rule_explanation: Optional[str] = None
    code_context_summary: Optional[str] = None

    def is_high_confidence(self, threshold: float = 0.8) -> bool:
        """確信度が閾値以上かどうかを確認する。

        Args:
            threshold: 確信度の閾値（デフォルト: 0.8）

        Returns:
            確信度が閾値以上の場合True
        """
        return self.confidence >= threshold

    def to_excel_dict(self) -> dict:
        """Excel出力用の辞書に変換する。

        Returns:
            Excel列の値を含む辞書
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
