"""Excel writer for classification results."""

from typing import Dict, List
from pathlib import Path
import shutil
import logging

from openpyxl import load_workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side

from ..models.classification import ClassificationResult, ClassificationType

logger = logging.getLogger(__name__)


class ExcelWriter:
    """Write classification results to Excel files."""

    # Colors for each classification type (RGB hex without #)
    CLASSIFICATION_COLORS: Dict[ClassificationType, str] = {
        ClassificationType.FALSE_POSITIVE: "C6EFCE",  # Green - no issue
        ClassificationType.DEVIATION: "FFEB9C",       # Yellow - needs review
        ClassificationType.FIX_REQUIRED: "FFC7CE",    # Red - needs fix
        ClassificationType.UNDETERMINED: "D9D9D9",    # Gray - could not determine
    }

    # Japanese column headers
    RESULT_HEADERS = ["分類", "分類理由", "確信度", "判定フェーズ"]

    def __init__(
        self,
        input_file: str,
        output_file: str,
        sheet_name: Optional[str] = None
    ):
        """Initialize the Excel writer.

        Args:
            input_file: Path to the input Excel file
            output_file: Path to the output Excel file
            sheet_name: Name of the sheet to modify (None for active sheet)
        """
        self.input_file = Path(input_file)
        self.output_file = Path(output_file)
        self.sheet_name = sheet_name

    def write_results(
        self,
        results: Dict[str, ClassificationResult],
        finding_id_to_row: Dict[str, int]
    ) -> None:
        """Write classification results to the Excel file.

        Args:
            results: Mapping of finding ID to classification result
            finding_id_to_row: Mapping of finding ID to Excel row number
        """
        # Copy input file to output
        shutil.copy(self.input_file, self.output_file)

        # Open the workbook
        wb = load_workbook(self.output_file)
        ws = wb.active if self.sheet_name is None else wb[self.sheet_name]

        # Find the last column
        last_col = ws.max_column

        # Add headers for result columns
        self._add_headers(ws, last_col)

        # Write results for each finding
        for finding_id, result in results.items():
            if finding_id not in finding_id_to_row:
                logger.warning(f"Finding {finding_id} not found in row mapping")
                continue

            row_num = finding_id_to_row[finding_id]
            self._write_result_row(ws, row_num, last_col, result)

        # Adjust column widths
        self._adjust_column_widths(ws, last_col)

        # Save the workbook
        wb.save(self.output_file)
        logger.info(f"Results written to {self.output_file}")

    def _add_headers(self, ws, last_col: int) -> None:
        """Add result column headers.

        Args:
            ws: Worksheet object
            last_col: Last existing column index
        """
        header_font = Font(bold=True)
        header_alignment = Alignment(horizontal="center", vertical="center")
        header_fill = PatternFill(
            start_color="4472C4",
            end_color="4472C4",
            fill_type="solid"
        )
        white_font = Font(bold=True, color="FFFFFF")
        thin_border = Border(
            left=Side(style="thin"),
            right=Side(style="thin"),
            top=Side(style="thin"),
            bottom=Side(style="thin")
        )

        for i, header in enumerate(self.RESULT_HEADERS, 1):
            cell = ws.cell(row=1, column=last_col + i)
            cell.value = header
            cell.font = white_font
            cell.alignment = header_alignment
            cell.fill = header_fill
            cell.border = thin_border

    def _write_result_row(
        self,
        ws,
        row_num: int,
        last_col: int,
        result: ClassificationResult
    ) -> None:
        """Write a single result row.

        Args:
            ws: Worksheet object
            row_num: Row number to write to
            last_col: Last existing column index
            result: Classification result to write
        """
        thin_border = Border(
            left=Side(style="thin"),
            right=Side(style="thin"),
            top=Side(style="thin"),
            bottom=Side(style="thin")
        )

        # Classification
        cell_classification = ws.cell(row=row_num, column=last_col + 1)
        cell_classification.value = result.classification.value
        cell_classification.fill = PatternFill(
            start_color=self.CLASSIFICATION_COLORS[result.classification],
            end_color=self.CLASSIFICATION_COLORS[result.classification],
            fill_type="solid"
        )
        cell_classification.alignment = Alignment(horizontal="center")
        cell_classification.border = thin_border

        # Reason
        cell_reason = ws.cell(row=row_num, column=last_col + 2)
        cell_reason.value = result.reason
        cell_reason.alignment = Alignment(wrap_text=True, vertical="top")
        cell_reason.border = thin_border

        # Confidence
        cell_confidence = ws.cell(row=row_num, column=last_col + 3)
        cell_confidence.value = f"{result.confidence:.0%}"
        cell_confidence.alignment = Alignment(horizontal="center")
        cell_confidence.border = thin_border

        # Phase
        cell_phase = ws.cell(row=row_num, column=last_col + 4)
        cell_phase.value = result.phase
        cell_phase.alignment = Alignment(horizontal="center")
        cell_phase.border = thin_border

    def _adjust_column_widths(self, ws, last_col: int) -> None:
        """Adjust column widths for result columns.

        Args:
            ws: Worksheet object
            last_col: Last existing column index
        """
        widths = [12, 60, 10, 12]  # Widths for each result column

        for i, width in enumerate(widths, 1):
            col_letter = ws.cell(row=1, column=last_col + i).column_letter
            ws.column_dimensions[col_letter].width = width

    def write_summary(self, results: List[ClassificationResult]) -> None:
        """Add a summary sheet with statistics.

        Args:
            results: List of all classification results
        """
        wb = load_workbook(self.output_file)

        # Remove existing Summary sheet if present
        if "Summary" in wb.sheetnames:
            del wb["Summary"]

        # Create new Summary sheet
        ws = wb.create_sheet("Summary")

        # Calculate statistics
        total = len(results)
        counts: Dict[ClassificationType, int] = {
            ClassificationType.FALSE_POSITIVE: 0,
            ClassificationType.DEVIATION: 0,
            ClassificationType.FIX_REQUIRED: 0,
            ClassificationType.UNDETERMINED: 0,
        }

        for result in results:
            counts[result.classification] += 1

        # Write title
        ws["A1"] = "分類結果サマリー"
        ws["A1"].font = Font(bold=True, size=14)
        ws.merge_cells("A1:C1")

        # Write timestamp
        from datetime import datetime
        ws["A2"] = f"生成日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        ws.merge_cells("A2:C2")

        # Write statistics table
        headers = ["分類", "件数", "割合"]
        header_font = Font(bold=True)
        thin_border = Border(
            left=Side(style="thin"),
            right=Side(style="thin"),
            top=Side(style="thin"),
            bottom=Side(style="thin")
        )

        for i, header in enumerate(headers, 1):
            cell = ws.cell(row=4, column=i)
            cell.value = header
            cell.font = header_font
            cell.border = thin_border
            cell.alignment = Alignment(horizontal="center")

        row = 5
        for classification_type, count in counts.items():
            # Classification name
            cell_type = ws.cell(row=row, column=1)
            cell_type.value = classification_type.value
            cell_type.fill = PatternFill(
                start_color=self.CLASSIFICATION_COLORS[classification_type],
                end_color=self.CLASSIFICATION_COLORS[classification_type],
                fill_type="solid"
            )
            cell_type.border = thin_border

            # Count
            cell_count = ws.cell(row=row, column=2)
            cell_count.value = count
            cell_count.alignment = Alignment(horizontal="right")
            cell_count.border = thin_border

            # Percentage
            cell_pct = ws.cell(row=row, column=3)
            cell_pct.value = f"{count / total * 100:.1f}%" if total > 0 else "0%"
            cell_pct.alignment = Alignment(horizontal="right")
            cell_pct.border = thin_border

            row += 1

        # Total row
        cell_total_label = ws.cell(row=row, column=1)
        cell_total_label.value = "合計"
        cell_total_label.font = Font(bold=True)
        cell_total_label.border = thin_border

        cell_total_count = ws.cell(row=row, column=2)
        cell_total_count.value = total
        cell_total_count.font = Font(bold=True)
        cell_total_count.alignment = Alignment(horizontal="right")
        cell_total_count.border = thin_border

        cell_total_pct = ws.cell(row=row, column=3)
        cell_total_pct.value = "100%"
        cell_total_pct.font = Font(bold=True)
        cell_total_pct.alignment = Alignment(horizontal="right")
        cell_total_pct.border = thin_border

        # Adjust column widths
        ws.column_dimensions["A"].width = 15
        ws.column_dimensions["B"].width = 10
        ws.column_dimensions["C"].width = 10

        wb.save(self.output_file)
        logger.info(f"Summary sheet added to {self.output_file}")


# Fix missing import
from typing import Optional
