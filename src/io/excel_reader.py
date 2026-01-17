"""Excel reader for CodeSonar reports."""

from typing import List, Generator, Optional, Dict
from pathlib import Path
import logging

import pandas as pd

from ..models.finding import Finding

logger = logging.getLogger(__name__)


class ExcelReader:
    """Read CodeSonar Excel reports and convert to Finding objects."""

    # Column name mappings for various Excel formats
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
        """Initialize the Excel reader.

        Args:
            file_path: Path to the Excel file
            sheet_name: Name of the sheet to read (None for first sheet)
            encoding: Character encoding for CSV files
        """
        self.file_path = Path(file_path)
        self.sheet_name = sheet_name
        self.encoding = encoding
        self._df: Optional[pd.DataFrame] = None
        self._column_map: Dict[str, str] = {}

    def read(self) -> List[Finding]:
        """Read all findings from the Excel file.

        Returns:
            List of Finding objects
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
        """Lazily read findings from the Excel file.

        Yields:
            Finding objects one at a time
        """
        self._load_dataframe()
        self._resolve_column_names()

        for idx, row in self._df.iterrows():
            try:
                yield self._row_to_finding(row, idx)
            except Exception as e:
                logger.warning(f"Failed to parse row {idx}: {e}")

    def _load_dataframe(self) -> None:
        """Load the DataFrame from the file."""
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

        # Remove empty rows
        self._df = self._df.dropna(how="all")

        logger.debug(f"Loaded DataFrame with {len(self._df)} rows")

    def _resolve_column_names(self) -> None:
        """Resolve column name mappings."""
        columns = self._df.columns.tolist()

        for standard_name, variants in self.COLUMN_MAPPINGS.items():
            for variant in variants:
                if variant in columns:
                    self._column_map[standard_name] = variant
                    break
            else:
                # Required columns
                if standard_name in ["file", "line", "rule", "message"]:
                    raise ValueError(
                        f"Required column not found: {standard_name}. "
                        f"Available columns: {columns}"
                    )

        logger.debug(f"Resolved column mappings: {self._column_map}")

    def _row_to_finding(self, row: pd.Series, row_index: int) -> Finding:
        """Convert a DataFrame row to a Finding object.

        Args:
            row: DataFrame row
            row_index: Row index (0-based)

        Returns:
            Finding object
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

        # Excel rows are 1-indexed, plus header row
        excel_row = row_index + 2
        return Finding.from_excel_row(row_dict, excel_row)

    def get_dataframe(self) -> pd.DataFrame:
        """Get the original DataFrame.

        Returns:
            Copy of the loaded DataFrame
        """
        self._load_dataframe()
        return self._df.copy()

    def get_row_count(self) -> int:
        """Get the number of data rows.

        Returns:
            Number of rows in the DataFrame
        """
        self._load_dataframe()
        return len(self._df)
