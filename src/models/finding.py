"""Finding model for static analysis results."""

from dataclasses import dataclass
from typing import Optional
from enum import Enum
import os


class Severity(Enum):
    """CodeSonar severity levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass
class SourceLocation:
    """Source code location information."""
    file_path: str
    line: int
    column: Optional[int] = None

    def __post_init__(self):
        # Normalize Windows paths
        self.file_path = os.path.normpath(self.file_path)

    def __str__(self) -> str:
        if self.column:
            return f"{self.file_path}:{self.line}:{self.column}"
        return f"{self.file_path}:{self.line}"


@dataclass
class Finding:
    """Static analysis finding information."""
    id: str
    location: SourceLocation
    rule_id: str
    message: str
    severity: Severity
    procedure: Optional[str] = None

    # Additional info populated during processing
    function_code: Optional[str] = None
    function_start_line: Optional[int] = None
    function_end_line: Optional[int] = None

    @classmethod
    def from_excel_row(cls, row: dict, row_index: int) -> "Finding":
        """Create a Finding from an Excel row dictionary.

        Args:
            row: Dictionary containing row data with keys:
                 File, Line, Rule, Message, Severity (optional), Procedure (optional)
            row_index: Row number in the Excel file (for ID generation)

        Returns:
            Finding instance
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
        """Parse severity from string or number.

        Args:
            value: Severity value (string or number)

        Returns:
            Severity enum value
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
