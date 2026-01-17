"""Prompt builder for LLM classification."""

from typing import Optional, Dict
import logging

from ..models.finding import Finding
from ..models.context import AnalysisContext, RuleInfo

logger = logging.getLogger(__name__)


class PromptBuilder:
    """Build prompts for LLM classification."""

    def __init__(self, rules_db: Optional[Dict[str, RuleInfo]] = None):
        """Initialize the prompt builder.

        Args:
            rules_db: Dictionary of rule ID to RuleInfo
        """
        self.rules_db = rules_db or {}

    def build_system_prompt(self) -> str:
        """Build the system prompt.

        Returns:
            System prompt string
        """
        return """あなたは車載組み込みソフトウェアの静的解析結果を評価する専門家です。
AUTOSAR C++14 Coding GuidelinesおよびCERT C++ Coding Standardに精通しています。

あなたの役割は、静的解析ツール（CodeSonar）が検出した指摘を以下の3つに分類することです：

## 分類基準

### FALSE_POSITIVE（誤検知）
静的解析ツールの誤検知です。以下の場合に該当します：
- コードは規約に準拠しているが、ツールが誤って違反と判定した
- ツールがコンテキストを正しく理解できていない
- コードの意図が明確で、実際には問題がない

### DEVIATION（逸脱）
意図的な規約からの逸脱で、正当な技術的理由がある場合です：
- パフォーマンス最適化のための意図的な逸脱
- ハードウェア制約による必要な逸脱
- 外部APIとの互換性のための逸脱
- 安全性を確保した上での意図的な設計判断
※ 逸脱には適切なドキュメントと承認が必要です

### FIX_REQUIRED（修正）
実際に修正が必要な問題です：
- 規約違反が存在し、修正すべき
- 潜在的なバグやセキュリティ問題
- 保守性・可読性の問題で修正が推奨される

## 判定のガイドライン

1. コードの文脈を慎重に分析してください
2. 該当するルールの意図と目的を考慮してください
3. AUTOSAR AP（Adaptive Platform）の車載環境を考慮してください
4. 確信度は正直に評価してください（不確かな場合は低く設定）
5. 日本語で詳細な理由を説明してください

## 出力形式
指定されたJSON形式で回答してください。"""

    def build_phase1_prompt(
        self,
        finding: Finding,
        context: AnalysisContext
    ) -> str:
        """Build Phase 1 user prompt.

        Args:
            finding: Finding to classify
            context: Analysis context with function code

        Returns:
            User prompt string
        """
        rule_info = self._get_rule_info(finding.rule_id, context.rule_info)

        relative_line = finding.location.line - context.target_function.start_line + 1

        prompt = f"""## 静的解析の指摘情報

**ファイル**: {finding.location.file_path}
**行番号**: {finding.location.line}
**ルールID**: {finding.rule_id}
**メッセージ**: {finding.message}
**重要度**: {finding.severity.value}

## ルール情報
{rule_info}

## 対象コード

以下は指摘行（{finding.location.line}行目）を含む関数のコードです：

```cpp
// ファイル: {context.target_function.file_path}
// 関数: {context.target_function.name}
// 行 {context.target_function.start_line} - {context.target_function.end_line}

{context.target_function.code}
```

**指摘箇所**: 上記コード内の {relative_line} 行目付近

## 判定してください

このコードと指摘内容を分析し、FALSE_POSITIVE（誤検知）、DEVIATION（逸脱）、FIX_REQUIRED（修正）のいずれかに分類してください。
確信度と詳細な理由も含めてください。"""

        return prompt

    def build_phase2_prompt(
        self,
        finding: Finding,
        context: AnalysisContext
    ) -> str:
        """Build Phase 2 user prompt with additional context.

        Args:
            finding: Finding to classify
            context: Analysis context with additional information

        Returns:
            User prompt string
        """
        rule_info = self._get_rule_info(finding.rule_id, context.rule_info)

        relative_line = finding.location.line - context.target_function.start_line + 1

        # Build caller functions section
        caller_section = ""
        if context.caller_functions:
            caller_section = "\n## 呼び出し元関数\n\n"
            for i, caller in enumerate(context.caller_functions, 1):
                caller_section += f"""### 呼び出し元 {i}: {caller.name}
```cpp
// ファイル: {caller.file_path}
// 行 {caller.start_line} - {caller.end_line}

{caller.code}
```

"""

        # Build type definitions section
        type_section = ""
        if context.related_types:
            type_section = "\n## 関連する型定義\n\n"
            for typedef in context.related_types:
                type_section += f"""### {typedef.kind} {typedef.name}
```cpp
// ファイル: {typedef.file_path}, 行 {typedef.line}

{typedef.code}
```

"""

        # Build macro definitions section
        macro_section = ""
        if context.related_macros:
            macro_section = "\n## 関連するマクロ定義\n\n"
            for macro in context.related_macros:
                macro_section += f"- `{macro.definition}` ({macro.file_path}:{macro.line})\n"

        prompt = f"""## 静的解析の指摘情報

**ファイル**: {finding.location.file_path}
**行番号**: {finding.location.line}
**ルールID**: {finding.rule_id}
**メッセージ**: {finding.message}
**重要度**: {finding.severity.value}

## ルール情報
{rule_info}

## 対象コード（指摘箇所を含む関数）

```cpp
// ファイル: {context.target_function.file_path}
// 関数: {context.target_function.name}
// 行 {context.target_function.start_line} - {context.target_function.end_line}

{context.target_function.code}
```

**指摘箇所**: 上記コード内の {relative_line} 行目付近
{caller_section}{type_section}{macro_section}
## 追加コンテキストを踏まえた判定

Phase 1では確信度が低かったため、追加のコンテキスト（呼び出し元、型定義、マクロ）を提供しています。
これらの情報を踏まえて、再度分類を行ってください。

特に以下の点に注目してください：
1. 呼び出し元でのパラメータの使われ方
2. 型定義から分かる制約や意図
3. マクロの展開結果がコードに与える影響"""

        return prompt

    def _get_rule_info(
        self,
        rule_id: str,
        context_rule_info: Optional[RuleInfo] = None
    ) -> str:
        """Get rule information as text.

        Args:
            rule_id: Rule ID to look up
            context_rule_info: Rule info from context (if available)

        Returns:
            Formatted rule information string
        """
        # Use context rule info if available
        if context_rule_info:
            return context_rule_info.to_prompt_text()

        # Try to find in rules database
        normalized_id = self._normalize_rule_id(rule_id)

        if rule_id in self.rules_db:
            return self.rules_db[rule_id].to_prompt_text()

        if normalized_id in self.rules_db:
            return self.rules_db[normalized_id].to_prompt_text()

        # Fallback message
        return f"※ルール {rule_id} の詳細情報はデータベースにありません。指摘メッセージを参考に判定してください。"

    def _normalize_rule_id(self, rule_id: str) -> str:
        """Normalize a rule ID.

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

    def set_rules_db(self, rules_db: Dict[str, RuleInfo]) -> None:
        """Set the rules database.

        Args:
            rules_db: Dictionary of rule ID to RuleInfo
        """
        self.rules_db = rules_db
        logger.info(f"Rules database set with {len(rules_db)} rules")
