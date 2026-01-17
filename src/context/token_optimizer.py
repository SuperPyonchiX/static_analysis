"""Token optimizer for LLM context."""

from typing import Optional, List
import logging

from ..models.context import AnalysisContext, FunctionInfo

logger = logging.getLogger(__name__)


class TokenOptimizer:
    """Optimize context to fit within token limits."""

    # GPT-5-mini token limit with safety margin
    DEFAULT_MAX_TOKENS = 250000

    # Base tokens for system prompt and formatting
    BASE_TOKENS = 2000

    # Average characters per token (Japanese/code mix)
    CHARS_PER_TOKEN = 3

    def __init__(self, max_tokens: int = DEFAULT_MAX_TOKENS):
        """Initialize the token optimizer.

        Args:
            max_tokens: Maximum input tokens allowed
        """
        self.max_tokens = max_tokens

    def optimize_context(self, context: AnalysisContext) -> AnalysisContext:
        """Optimize context to fit within token limits.

        Args:
            context: Original analysis context

        Returns:
            Optimized analysis context
        """
        available_tokens = self.max_tokens - self.BASE_TOKENS

        # Calculate budget allocation
        # Priority: target function > callers > types > macros
        target_budget = int(available_tokens * 0.6)
        caller_budget = int(available_tokens * 0.25)
        type_budget = int(available_tokens * 0.10)
        macro_budget = int(available_tokens * 0.05)

        # Optimize target function
        target_tokens = self._estimate_tokens(context.target_function.code)

        if target_tokens > target_budget:
            logger.debug(
                f"Target function too large ({target_tokens} tokens), truncating"
            )
            context.target_function = self._truncate_function(
                context.target_function,
                context.finding_line,
                target_budget
            )
            target_tokens = self._estimate_tokens(context.target_function.code)

        # Adjust remaining budgets based on actual target usage
        remaining = available_tokens - target_tokens
        caller_budget = int(remaining * 0.5)
        type_budget = int(remaining * 0.3)
        macro_budget = int(remaining * 0.2)

        # Optimize callers
        if context.caller_functions:
            context.caller_functions = self._optimize_functions(
                context.caller_functions,
                caller_budget
            )

        # Optimize types
        if context.related_types:
            context.related_types = self._optimize_items(
                context.related_types,
                type_budget,
                key=lambda t: len(t.code)
            )

        # Optimize macros
        if context.related_macros:
            context.related_macros = self._optimize_items(
                context.related_macros,
                macro_budget,
                key=lambda m: len(m.definition)
            )

        final_tokens = context.estimate_tokens()
        logger.debug(
            f"Context optimized: {final_tokens} tokens "
            f"(limit: {self.max_tokens})"
        )

        return context

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count for text.

        Args:
            text: Text to estimate

        Returns:
            Estimated token count
        """
        return len(text) // self.CHARS_PER_TOKEN

    def _truncate_function(
        self,
        func: FunctionInfo,
        focus_line: int,
        max_tokens: int
    ) -> FunctionInfo:
        """Truncate a function to fit token budget.

        Keeps the finding line in context.

        Args:
            func: Function to truncate
            focus_line: Line to keep in view
            max_tokens: Maximum tokens allowed

        Returns:
            Truncated FunctionInfo
        """
        lines = func.code.split("\n")
        max_chars = max_tokens * self.CHARS_PER_TOKEN

        # Calculate relative line position
        relative_line = focus_line - func.start_line

        # Start from the focus line and expand outward
        result_lines = []
        current_chars = 0

        # Determine center range
        center_start = max(0, relative_line - 50)
        center_end = min(len(lines), relative_line + 50)

        for i in range(center_start, center_end):
            line = lines[i]
            if current_chars + len(line) + 1 > max_chars:
                break
            result_lines.append(line)
            current_chars += len(line) + 1

        # Add truncation markers
        if center_start > 0:
            start_marker = (
                f"// ... (省略: 行 {func.start_line} - "
                f"{func.start_line + center_start - 1})"
            )
            result_lines.insert(0, start_marker)

        actual_end = center_start + len(result_lines)
        if actual_end < len(lines):
            end_marker = (
                f"// ... (省略: 行 {func.start_line + actual_end} - "
                f"{func.end_line})"
            )
            result_lines.append(end_marker)

        truncated_code = "\n".join(result_lines)

        return FunctionInfo(
            name=func.name,
            file_path=func.file_path,
            start_line=func.start_line + center_start,
            end_line=func.start_line + actual_end,
            code=truncated_code,
            signature=func.signature,
            return_type=func.return_type,
            parameters=func.parameters
        )

    def _optimize_functions(
        self,
        functions: List[FunctionInfo],
        budget: int
    ) -> List[FunctionInfo]:
        """Optimize a list of functions to fit budget.

        Args:
            functions: List of functions
            budget: Token budget

        Returns:
            Optimized list of functions
        """
        result = []
        used_tokens = 0

        for func in functions:
            tokens = self._estimate_tokens(func.code)

            if used_tokens + tokens <= budget:
                result.append(func)
                used_tokens += tokens
            else:
                # Try to fit a truncated version
                remaining = budget - used_tokens
                if remaining > 100:  # Minimum useful size
                    truncated = self._truncate_caller(func, remaining)
                    if truncated:
                        result.append(truncated)
                break

        return result

    def _truncate_caller(
        self,
        func: FunctionInfo,
        max_tokens: int
    ) -> Optional[FunctionInfo]:
        """Truncate a caller function.

        Args:
            func: Function to truncate
            max_tokens: Maximum tokens

        Returns:
            Truncated function or None if too small
        """
        if max_tokens < 50:
            return None

        lines = func.code.split("\n")
        max_chars = max_tokens * self.CHARS_PER_TOKEN

        result_lines = []
        current_chars = 0

        # Keep first lines (signature and initial code)
        for line in lines[:30]:
            if current_chars + len(line) + 1 > max_chars:
                break
            result_lines.append(line)
            current_chars += len(line) + 1

        if len(result_lines) < len(lines):
            result_lines.append("// ... (以下省略)")

        return FunctionInfo(
            name=func.name,
            file_path=func.file_path,
            start_line=func.start_line,
            end_line=func.start_line + len(result_lines),
            code="\n".join(result_lines),
            signature=func.signature
        )

    def _optimize_items(
        self,
        items: list,
        budget: int,
        key
    ) -> list:
        """Optimize a list of items to fit budget.

        Prioritizes smaller items.

        Args:
            items: List of items
            budget: Token budget
            key: Function to get size of item

        Returns:
            Optimized list
        """
        # Sort by size (smaller first)
        sorted_items = sorted(items, key=key)

        result = []
        used_tokens = 0

        for item in sorted_items:
            tokens = self._estimate_tokens(str(key(item)))

            if used_tokens + tokens <= budget:
                result.append(item)
                used_tokens += tokens

        return result

    def estimate_prompt_tokens(
        self,
        system_prompt: str,
        user_prompt: str
    ) -> int:
        """Estimate total prompt tokens.

        Args:
            system_prompt: System prompt
            user_prompt: User prompt

        Returns:
            Estimated token count
        """
        total_chars = len(system_prompt) + len(user_prompt)
        return total_chars // self.CHARS_PER_TOKEN

    def will_fit(self, context: AnalysisContext) -> bool:
        """Check if context will fit within limits.

        Args:
            context: Analysis context

        Returns:
            True if context fits
        """
        estimated = context.estimate_tokens() + self.BASE_TOKENS
        return estimated <= self.max_tokens
