"""静的解析結果の指摘情報モデル。"""

from dataclasses import dataclass
from typing import Optional
from enum import Enum
import os


class Severity(Enum):
    """CodeSonarの重大度レベル。"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass
class SourceLocation:
    """ソースコードの位置情報。"""
    file_path: str
    line: int
    column: Optional[int] = None

    def __post_init__(self):
        # Windowsパスを正規化
        self.file_path = os.path.normpath(self.file_path)

    def __str__(self) -> str:
        if self.column:
            return f"{self.file_path}:{self.line}:{self.column}"
        return f"{self.file_path}:{self.line}"


@dataclass
class Finding:
    """静的解析の指摘情報。"""
    id: str
    location: SourceLocation
    rule_id: str
    message: str
    severity: Severity
    procedure: Optional[str] = None

    # 処理中に追加される情報
    function_code: Optional[str] = None
    function_start_line: Optional[int] = None
    function_end_line: Optional[int] = None

    @classmethod
    def from_excel_row(cls, row: dict, row_index: int) -> "Finding":
        """Excel行の辞書からFindingを生成する。

        Args:
            row: 行データを含む辞書。キー: File, Line, Rule, Message,
                 Severity（任意）, Procedure（任意）
            row_index: Excelファイル内の行番号（ID生成用）

        Returns:
            Findingインスタンス
        """
        return cls(
            id=f"F{row_index:05d}",
            location=SourceLocation(
                file_path=str(row["File"]),
                line=int(row["Line"])
            ),
            rule_id=str(row["Rule"]),
            message=str(row["Message"]),
            severity=cls._parse_severity(row.get("Severity", row.get("Priority", "medium"))),
            procedure=row.get("Procedure", row.get("Function"))
        )

    @staticmethod
    def _parse_severity(value) -> Severity:
        """文字列または数値から重大度をパースする。

        Args:
            value: 重大度の値（文字列または数値）

        Returns:
            Severity列挙値
        """
        if value is None:
            return Severity.MEDIUM

        value_str = str(value).lower().strip()

        mapping = {
            "critical": Severity.CRITICAL,
            "high": Severity.HIGH,
            "medium": Severity.MEDIUM,
            "low": Severity.LOW,
            "info": Severity.INFO,
            "information": Severity.INFO,
            "1": Severity.CRITICAL,
            "2": Severity.HIGH,
            "3": Severity.MEDIUM,
            "4": Severity.LOW,
            "5": Severity.INFO,
        }

        return mapping.get(value_str, Severity.MEDIUM)

    def __str__(self) -> str:
        return f"[{self.id}] {self.rule_id} at {self.location}: {self.message[:50]}..."
