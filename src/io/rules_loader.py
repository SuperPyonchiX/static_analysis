"""Rules database loader for AUTOSAR/CERT C++ rules."""

from typing import Dict, List, Optional, Any
from pathlib import Path
import logging

import pandas as pd
import yaml

from ..models.context import RuleInfo

logger = logging.getLogger(__name__)


class RulesLoader:
    """Load rules from various sources (Excel, CSV, YAML)."""

    def __init__(self):
        """Initialize the rules loader."""
        self._rules: Dict[str, RuleInfo] = {}

    def load(self, config: dict) -> Dict[str, RuleInfo]:
        """Load rules based on configuration.

        Args:
            config: Rules source configuration with keys:
                - type: "excel", "csv", or "yaml"
                - path: Path to the rules file
                - sheet: Sheet name for Excel (optional)
                - columns: Column mapping (optional)

        Returns:
            Dictionary mapping rule ID to RuleInfo
        """
        source_type = config.get("type", "yaml").lower()
        path = config.get("path")

        if not path:
            logger.warning("No rules source path specified")
            return {}

        path = Path(path)
        if not path.exists():
            logger.warning(f"Rules file not found: {path}")
            return {}

        if source_type == "excel":
            return self.load_from_excel(
                str(path),
                sheet=config.get("sheet"),
                columns=config.get("columns", {})
            )
        elif source_type == "csv":
            return self.load_from_csv(
                str(path),
                columns=config.get("columns", {})
            )
        elif source_type == "yaml":
            return self.load_from_yaml(str(path))
        else:
            raise ValueError(f"Unsupported rules source type: {source_type}")

    def load_from_excel(
        self,
        path: str,
        sheet: Optional[str] = None,
        columns: Optional[Dict[str, str]] = None
    ) -> Dict[str, RuleInfo]:
        """Load rules from an Excel file.

        Args:
            path: Path to the Excel file
            sheet: Sheet name (None for first sheet)
            columns: Column name mapping

        Returns:
            Dictionary mapping rule ID to RuleInfo
        """
        columns = columns or {}

        # Default column mappings
        col_rule_id = columns.get("rule_id", "Rule ID")
        col_title = columns.get("title", "Title")
        col_category = columns.get("category", "Category")
        col_rationale = columns.get("rationale", "Rationale")
        col_hints = columns.get("hints", "False Positive Hints")

        df = pd.read_excel(path, sheet_name=sheet or 0)

        rules = {}
        for _, row in df.iterrows():
            try:
                rule_id = str(row.get(col_rule_id, "")).strip()
                if not rule_id:
                    continue

                # Parse hints (may be semicolon or newline separated)
                hints_raw = row.get(col_hints, "")
                hints = self._parse_hints(hints_raw)

                rule_info = RuleInfo(
                    rule_id=rule_id,
                    title=str(row.get(col_title, "")),
                    category=str(row.get(col_category, "")),
                    rationale=str(row.get(col_rationale, "")),
                    false_positive_hints=hints
                )

                rules[rule_id] = rule_info
                # Also store with normalized ID
                normalized_id = self._normalize_rule_id(rule_id)
                if normalized_id != rule_id:
                    rules[normalized_id] = rule_info

            except Exception as e:
                logger.warning(f"Failed to parse rule row: {e}")

        logger.info(f"Loaded {len(rules)} rules from Excel: {path}")
        return rules

    def load_from_csv(
        self,
        path: str,
        columns: Optional[Dict[str, str]] = None,
        encoding: str = "utf-8"
    ) -> Dict[str, RuleInfo]:
        """Load rules from a CSV file.

        Args:
            path: Path to the CSV file
            columns: Column name mapping
            encoding: File encoding

        Returns:
            Dictionary mapping rule ID to RuleInfo
        """
        columns = columns or {}

        col_rule_id = columns.get("rule_id", "Rule ID")
        col_title = columns.get("title", "Title")
        col_category = columns.get("category", "Category")
        col_rationale = columns.get("rationale", "Rationale")
        col_hints = columns.get("hints", "False Positive Hints")

        df = pd.read_csv(path, encoding=encoding)

        rules = {}
        for _, row in df.iterrows():
            try:
                rule_id = str(row.get(col_rule_id, "")).strip()
                if not rule_id:
                    continue

                hints = self._parse_hints(row.get(col_hints, ""))

                rule_info = RuleInfo(
                    rule_id=rule_id,
                    title=str(row.get(col_title, "")),
                    category=str(row.get(col_category, "")),
                    rationale=str(row.get(col_rationale, "")),
                    false_positive_hints=hints
                )

                rules[rule_id] = rule_info
                normalized_id = self._normalize_rule_id(rule_id)
                if normalized_id != rule_id:
                    rules[normalized_id] = rule_info

            except Exception as e:
                logger.warning(f"Failed to parse rule row: {e}")

        logger.info(f"Loaded {len(rules)} rules from CSV: {path}")
        return rules

    def load_from_yaml(self, path: str) -> Dict[str, RuleInfo]:
        """Load rules from a YAML file.

        Expected YAML format:
        ```yaml
        rules:
          A5-1-1:
            title: "Rule title"
            category: "Required"
            rationale: "Why this rule exists"
            false_positive_hints:
              - "Hint 1"
              - "Hint 2"
        ```

        Args:
            path: Path to the YAML file

        Returns:
            Dictionary mapping rule ID to RuleInfo
        """
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data or "rules" not in data:
            logger.warning(f"No 'rules' key found in YAML: {path}")
            return {}

        rules = {}
        for rule_id, rule_data in data["rules"].items():
            try:
                hints = rule_data.get("false_positive_hints", [])
                if isinstance(hints, str):
                    hints = self._parse_hints(hints)

                rule_info = RuleInfo(
                    rule_id=str(rule_id),
                    title=str(rule_data.get("title", "")),
                    category=str(rule_data.get("category", "")),
                    rationale=str(rule_data.get("rationale", "")),
                    false_positive_hints=hints
                )

                rules[rule_id] = rule_info
                normalized_id = self._normalize_rule_id(rule_id)
                if normalized_id != rule_id:
                    rules[normalized_id] = rule_info

            except Exception as e:
                logger.warning(f"Failed to parse rule {rule_id}: {e}")

        logger.info(f"Loaded {len(rules)} rules from YAML: {path}")
        return rules

    def _parse_hints(self, hints_raw: Any) -> List[str]:
        """Parse hints from various formats.

        Args:
            hints_raw: Raw hints value (string, list, or None)

        Returns:
            List of hint strings
        """
        if hints_raw is None or (isinstance(hints_raw, float) and pd.isna(hints_raw)):
            return []

        if isinstance(hints_raw, list):
            return [str(h).strip() for h in hints_raw if h]

        hints_str = str(hints_raw)

        # Try newline separator first
        if "\n" in hints_str:
            hints = [h.strip() for h in hints_str.split("\n")]
        # Then try semicolon
        elif ";" in hints_str:
            hints = [h.strip() for h in hints_str.split(";")]
        # Finally comma
        elif "," in hints_str:
            hints = [h.strip() for h in hints_str.split(",")]
        else:
            hints = [hints_str.strip()] if hints_str.strip() else []

        return [h for h in hints if h]

    def _normalize_rule_id(self, rule_id: str) -> str:
        """Normalize a rule ID by removing common prefixes.

        Args:
            rule_id: Original rule ID

        Returns:
            Normalized rule ID
        """
        prefixes = ["AUTOSAR-", "CERT-", "MISRA-", "A-", "M-"]
        normalized = rule_id.upper()

        for prefix in prefixes:
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix):]
                break

        return normalized

    def get_rule(self, rule_id: str) -> Optional[RuleInfo]:
        """Get rule info by ID.

        Args:
            rule_id: Rule ID to look up

        Returns:
            RuleInfo or None if not found
        """
        # Try exact match first
        if rule_id in self._rules:
            return self._rules[rule_id]

        # Try normalized ID
        normalized = self._normalize_rule_id(rule_id)
        return self._rules.get(normalized)

    def merge_rules(self, new_rules: Dict[str, RuleInfo]) -> None:
        """Merge new rules into the existing rules.

        Args:
            new_rules: Rules to merge
        """
        self._rules.update(new_rules)

    @property
    def rules(self) -> Dict[str, RuleInfo]:
        """Get all loaded rules."""
        return self._rules
