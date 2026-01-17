"""Context builder for LLM analysis."""

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
    """Build analysis context for LLM classification."""

    def __init__(
        self,
        clang_analyzer: ClangAnalyzer,
        source_files: List[str],
        rules_db: Optional[Dict[str, RuleInfo]] = None
    ):
        """Initialize the context builder.

        Args:
            clang_analyzer: ClangAnalyzer instance
            source_files: List of project source files
            rules_db: Optional rules database
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
        """Build Phase 1 context (target function only).

        Args:
            finding: Finding to build context for

        Returns:
            AnalysisContext or None if extraction fails
        """
        # Extract function containing the finding
        func_info = self.function_extractor.extract_function_at_line(
            finding.location.file_path,
            finding.location.line
        )

        if func_info is None:
            # Try to get context lines as fallback
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

        # Get rule info
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
        """Build Phase 2 context with additional information.

        Args:
            finding: Finding to build context for
            phase1_context: Context from Phase 1
            max_callers: Maximum number of callers to include
            max_types: Maximum number of type definitions
            max_macros: Maximum number of macro definitions

        Returns:
            Enhanced AnalysisContext
        """
        # Create new context with Phase 1 data
        context = AnalysisContext(
            target_function=phase1_context.target_function,
            finding_line=phase1_context.finding_line,
            rule_info=phase1_context.rule_info
        )

        # Add callers if we have a real function
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

        # Add related types
        try:
            context.related_types = self.symbol_resolver.find_types_in_function(
                phase1_context.target_function.code,
                finding.location.file_path,
                max_types=max_types
            )
            logger.debug(f"Found {len(context.related_types)} related types")
        except Exception as e:
            logger.warning(f"Failed to find types: {e}")

        # Add related macros
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
        """Get rule information from the database.

        Args:
            rule_id: Rule ID to look up

        Returns:
            RuleInfo or None if not found
        """
        # Try exact match
        if rule_id in self.rules_db:
            return self.rules_db[rule_id]

        # Try normalized ID
        normalized = self._normalize_rule_id(rule_id)
        if normalized in self.rules_db:
            return self.rules_db[normalized]

        return None

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
