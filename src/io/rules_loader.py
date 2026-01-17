"""AUTOSAR/CERT C++ルールのデータベースローダー。"""

from typing import Dict, List, Optional, Any
from pathlib import Path
import logging

import pandas as pd
import yaml

from ..models.context import RuleInfo

logger = logging.getLogger(__name__)


class RulesLoader:
    """各種ソース（Excel, CSV, YAML）からルールを読み込む。"""

    def __init__(self):
        """ルールローダーを初期化する。"""
        self._rules: Dict[str, RuleInfo] = {}

    def load(self, config: dict) -> Dict[str, RuleInfo]:
        """設定に基づいてルールを読み込む。

        Args:
            config: ルールソース設定（キー:
                - type: "excel", "csv", または "yaml"
                - path: ルールファイルのパス
                - sheet: Excelのシート名（任意）
                - columns: 列マッピング（任意））

        Returns:
            ルールIDからRuleInfoへの辞書
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
        """Excelファイルからルールを読み込む。

        Args:
            path: Excelファイルのパス
            sheet: シート名（Noneの場合は最初のシート）
            columns: 列名マッピング

        Returns:
            ルールIDからRuleInfoへの辞書
        """
        columns = columns or {}

        # デフォルトの列マッピング
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

                # ヒントをパース（セミコロンまたは改行区切りの可能性あり）
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
                # 正規化されたIDでも保存
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
        """CSVファイルからルールを読み込む。

        Args:
            path: CSVファイルのパス
            columns: 列名マッピング
            encoding: ファイルエンコーディング

        Returns:
            ルールIDからRuleInfoへの辞書
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
        """YAMLファイルからルールを読み込む。

        想定されるYAML形式:
        ```yaml
        rules:
          A5-1-1:
            title: "ルールタイトル"
            category: "Required"
            rationale: "このルールの根拠"
            false_positive_hints:
              - "ヒント1"
              - "ヒント2"
        ```

        Args:
            path: YAMLファイルのパス

        Returns:
            ルールIDからRuleInfoへの辞書
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
        """各種形式からヒントをパースする。

        Args:
            hints_raw: 生のヒント値（文字列、リスト、またはNone）

        Returns:
            ヒント文字列のリスト
        """
        if hints_raw is None or (isinstance(hints_raw, float) and pd.isna(hints_raw)):
            return []

        if isinstance(hints_raw, list):
            return [str(h).strip() for h in hints_raw if h]

        hints_str = str(hints_raw)

        # まず改行区切りを試す
        if "\n" in hints_str:
            hints = [h.strip() for h in hints_str.split("\n")]
        # 次にセミコロンを試す
        elif ";" in hints_str:
            hints = [h.strip() for h in hints_str.split(";")]
        # 最後にカンマを試す
        elif "," in hints_str:
            hints = [h.strip() for h in hints_str.split(",")]
        else:
            hints = [hints_str.strip()] if hints_str.strip() else []

        return [h for h in hints if h]

    def _normalize_rule_id(self, rule_id: str) -> str:
        """一般的なプレフィックスを除去してルールIDを正規化する。

        Args:
            rule_id: 元のルールID

        Returns:
            正規化されたルールID
        """
        prefixes = ["AUTOSAR-", "CERT-", "MISRA-", "A-", "M-"]
        normalized = rule_id.upper()

        for prefix in prefixes:
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix):]
                break

        return normalized

    def get_rule(self, rule_id: str) -> Optional[RuleInfo]:
        """IDでルール情報を取得する。

        Args:
            rule_id: 検索するルールID

        Returns:
            RuleInfo、見つからない場合はNone
        """
        # まず完全一致を試す
        if rule_id in self._rules:
            return self._rules[rule_id]

        # 正規化されたIDで試す
        normalized = self._normalize_rule_id(rule_id)
        return self._rules.get(normalized)

    def merge_rules(self, new_rules: Dict[str, RuleInfo]) -> None:
        """新しいルールを既存のルールにマージする。

        Args:
            new_rules: マージするルール
        """
        self._rules.update(new_rules)

    @property
    def rules(self) -> Dict[str, RuleInfo]:
        """読み込み済みの全ルールを取得する。"""
        return self._rules
