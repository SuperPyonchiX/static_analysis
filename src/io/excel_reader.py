"""CodeSonarレポートのExcel読み込みモジュール。"""

from typing import List, Generator, Optional, Dict
from pathlib import Path
import logging

import pandas as pd

from ..models.finding import Finding

logger = logging.getLogger(__name__)


class ExcelReader:
    """CodeSonar Excelレポートを読み込み、Findingオブジェクトに変換する。"""

    # 各種Excel形式用の列名マッピング
    COLUMN_MAPPINGS: Dict[str, List[str]] = {
        "file": ["File", "ファイル", "file", "FILE", "Source File", "SourceFile"],
        "line": ["Line", "行", "line", "LINE", "Line Number", "LineNumber"],
        "rule": ["Rule", "ルール", "rule", "RULE", "Rule ID", "RuleID", "Warning Class"],
        "message": ["Message", "メッセージ", "message", "MESSAGE", "Description"],
        "severity": ["Severity", "Priority", "重要度", "優先度", "severity", "priority"],
        "procedure": [
            "Procedure", "Function", "関数", "procedure", "function",
            "Procedure/Function", "ProcedureFunction"
        ]
    }

    def __init__(
        self,
        file_path: str,
        sheet_name: Optional[str] = None,
        encoding: str = "utf-8"
    ):
        """Excelリーダーを初期化する。

        Args:
            file_path: Excelファイルのパス
            sheet_name: 読み込むシート名（Noneの場合は最初のシート）
            encoding: CSVファイルの文字エンコーディング
        """
        self.file_path = Path(file_path)
        self.sheet_name = sheet_name
        self.encoding = encoding
        self._df: Optional[pd.DataFrame] = None
        self._column_map: Dict[str, str] = {}

    def read(self) -> List[Finding]:
        """Excelファイルから全ての指摘を読み込む。

        Returns:
            Findingオブジェクトのリスト
        """
        self._load_dataframe()
        self._resolve_column_names()

        findings = []
        for idx, row in self._df.iterrows():
            try:
                finding = self._row_to_finding(row, idx)
                findings.append(finding)
            except Exception as e:
                logger.warning(f"Failed to parse row {idx}: {e}")

        logger.info(f"Loaded {len(findings)} findings from {self.file_path}")
        return findings

    def read_lazy(self) -> Generator[Finding, None, None]:
        """Excelファイルから指摘を遅延読み込みする。

        Yields:
            Findingオブジェクトを1件ずつ返す
        """
        self._load_dataframe()
        self._resolve_column_names()

        for idx, row in self._df.iterrows():
            try:
                yield self._row_to_finding(row, idx)
            except Exception as e:
                logger.warning(f"Failed to parse row {idx}: {e}")

    def _load_dataframe(self) -> None:
        """ファイルからDataFrameを読み込む。"""
        if self._df is not None:
            return

        suffix = self.file_path.suffix.lower()

        if suffix in [".xlsx", ".xlsm"]:
            self._df = pd.read_excel(
                self.file_path,
                sheet_name=self.sheet_name or 0,
                engine="openpyxl"
            )
        elif suffix == ".xls":
            self._df = pd.read_excel(
                self.file_path,
                sheet_name=self.sheet_name or 0,
                engine="xlrd"
            )
        elif suffix == ".csv":
            self._df = pd.read_csv(
                self.file_path,
                encoding=self.encoding
            )
        else:
            raise ValueError(f"Unsupported file format: {suffix}")

        # 空行を削除
        self._df = self._df.dropna(how="all")

        logger.debug(f"Loaded DataFrame with {len(self._df)} rows")

    def _resolve_column_names(self) -> None:
        """列名マッピングを解決する。"""
        columns = self._df.columns.tolist()

        for standard_name, variants in self.COLUMN_MAPPINGS.items():
            for variant in variants:
                if variant in columns:
                    self._column_map[standard_name] = variant
                    break
            else:
                # 必須列
                if standard_name in ["file", "line", "rule", "message"]:
                    raise ValueError(
                        f"必須列が見つかりません: {standard_name}。"
                        f"利用可能な列: {columns}"
                    )

        logger.debug(f"Resolved column mappings: {self._column_map}")

    def _row_to_finding(self, row: pd.Series, row_index: int) -> Finding:
        """DataFrameの行をFindingオブジェクトに変換する。

        Args:
            row: DataFrameの行
            row_index: 行インデックス（0始まり）

        Returns:
            Findingオブジェクト
        """
        row_dict = {
            "File": str(row[self._column_map["file"]]),
            "Line": row[self._column_map["line"]],
            "Rule": str(row[self._column_map["rule"]]),
            "Message": str(row[self._column_map["message"]]),
        }

        if "severity" in self._column_map:
            row_dict["Severity"] = str(row[self._column_map["severity"]])

        if "procedure" in self._column_map:
            proc_value = row[self._column_map["procedure"]]
            if pd.notna(proc_value):
                row_dict["Procedure"] = str(proc_value)

        # Excelの行は1始まり、ヘッダー行も含む
        excel_row = row_index + 2
        return Finding.from_excel_row(row_dict, excel_row)

    def get_dataframe(self) -> pd.DataFrame:
        """元のDataFrameを取得する。

        Returns:
            読み込んだDataFrameのコピー
        """
        self._load_dataframe()
        return self._df.copy()

    def get_row_count(self) -> int:
        """データ行数を取得する。

        Returns:
            DataFrameの行数
        """
        self._load_dataframe()
        return len(self._df)
