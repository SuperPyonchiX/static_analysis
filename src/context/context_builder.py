"""LLM解析用のコンテキストビルダー。"""

from typing import List, Optional, Dict
import logging

from ..models.finding import Finding
from ..models.context import AnalysisContext, FunctionInfo, RuleInfo
from ..analyzer.clang_analyzer import ClangAnalyzer
from ..analyzer.function_extractor import FunctionExtractor
from ..analyzer.caller_tracker import CallerTracker
from ..analyzer.symbol_resolver import SymbolResolver

logger = logging.getLogger(__name__)


class ContextBuilder:
    """LLM分類用の解析コンテキストを構築する。"""

    def __init__(
        self,
        clang_analyzer: ClangAnalyzer,
        source_files: List[str],
        rules_db: Optional[Dict[str, RuleInfo]] = None
    ):
        """コンテキストビルダーを初期化する。

        Args:
            clang_analyzer: ClangAnalyzerインスタンス
            source_files: プロジェクトのソースファイルリスト
            rules_db: 任意のルールデータベース
        """
        self.analyzer = clang_analyzer
        self.source_files = source_files
        self.rules_db = rules_db or {}

        self.function_extractor = FunctionExtractor(clang_analyzer)
        self.caller_tracker = CallerTracker(clang_analyzer, source_files)
        self.symbol_resolver = SymbolResolver(clang_analyzer)

        logger.info(
            f"ContextBuilder initialized with {len(source_files)} source files"
        )

    def build_phase1_context(
        self,
        finding: Finding
    ) -> Optional[AnalysisContext]:
        """Phase 1コンテキスト（対象関数のみ）を構築する。

        Args:
            finding: コンテキストを構築する指摘

        Returns:
            AnalysisContext、抽出失敗時はNone
        """
        # 指摘を含む関数を抽出
        func_info = self.function_extractor.extract_function_at_line(
            finding.location.file_path,
            finding.location.line
        )

        if func_info is None:
            # フォールバックとしてコンテキスト行を取得
            func_info, code = self.function_extractor.extract_function_with_context(
                finding.location.file_path,
                finding.location.line,
                context_lines=20
            )

            if func_info is None:
                logger.warning(
                    f"Could not extract context for {finding.id} "
                    f"at {finding.location}"
                )
                return None

        # ルール情報を取得
        rule_info = self._get_rule_info(finding.rule_id)

        return AnalysisContext(
            target_function=func_info,
            finding_line=finding.location.line,
            rule_info=rule_info
        )

    def build_phase2_context(
        self,
        finding: Finding,
        phase1_context: AnalysisContext,
        max_callers: int = 2,
        max_types: int = 5,
        max_macros: int = 5
    ) -> AnalysisContext:
        """追加情報を含むPhase 2コンテキストを構築する。

        Args:
            finding: コンテキストを構築する指摘
            phase1_context: Phase 1からのコンテキスト
            max_callers: 含める呼び出し元の最大数
            max_types: 型定義の最大数
            max_macros: マクロ定義の最大数

        Returns:
            拡張されたAnalysisContext
        """
        # Phase 1データで新しいコンテキストを作成
        context = AnalysisContext(
            target_function=phase1_context.target_function,
            finding_line=phase1_context.finding_line,
            rule_info=phase1_context.rule_info
        )

        # 実際の関数がある場合は呼び出し元を追加
        if phase1_context.target_function.name != "<context>":
            try:
                context.caller_functions = self.caller_tracker.find_callers(
                    phase1_context.target_function.name,
                    finding.location.file_path,
                    max_depth=1,
                    max_callers=max_callers
                )
                logger.debug(
                    f"Found {len(context.caller_functions)} callers for "
                    f"{phase1_context.target_function.name}"
                )
            except Exception as e:
                logger.warning(f"Failed to find callers: {e}")

        # 関連する型を追加
        try:
            context.related_types = self.symbol_resolver.find_types_in_function(
                phase1_context.target_function.code,
                finding.location.file_path,
                max_types=max_types
            )
            logger.debug(f"Found {len(context.related_types)} related types")
        except Exception as e:
            logger.warning(f"Failed to find types: {e}")

        # 関連するマクロを追加
        try:
            context.related_macros = self.symbol_resolver.find_macros_in_code(
                phase1_context.target_function.code,
                finding.location.file_path,
                max_macros=max_macros
            )
            logger.debug(f"Found {len(context.related_macros)} related macros")
        except Exception as e:
            logger.warning(f"Failed to find macros: {e}")

        return context

    def _get_rule_info(self, rule_id: str) -> Optional[RuleInfo]:
        """データベースからルール情報を取得する。

        Args:
            rule_id: 検索するルールID

        Returns:
            RuleInfo、見つからない場合はNone
        """
        # 完全一致を試す
        if rule_id in self.rules_db:
            return self.rules_db[rule_id]

        # 正規化されたIDで試す
        normalized = self._normalize_rule_id(rule_id)
        if normalized in self.rules_db:
            return self.rules_db[normalized]

        return None

    def _normalize_rule_id(self, rule_id: str) -> str:
        """ルールIDを正規化する。

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

    def set_rules_db(self, rules_db: Dict[str, RuleInfo]) -> None:
        """ルールデータベースを設定する。

        Args:
            rules_db: ルールIDからRuleInfoへの辞書
        """
        self.rules_db = rules_db
        logger.info(f"Rules database set with {len(rules_db)} rules")
