"""Context models for LLM analysis."""

from dataclasses import dataclass, field
from typing import List, Optional, Dict


@dataclass
class FunctionInfo:
    """Function information extracted from source code."""
    name: str
    file_path: str
    start_line: int
    end_line: int
    code: str
    signature: Optional[str] = None
    return_type: Optional[str] = None
    parameters: List[str] = field(default_factory=list)

    def line_count(self) -> int:
        """Get the number of lines in the function."""
        return self.end_line - self.start_line + 1

    def __str__(self) -> str:
        return f"{self.name} ({self.file_path}:{self.start_line}-{self.end_line})"


@dataclass
class TypeDefinition:
    """Type definition information (class, struct, enum, typedef)."""
    name: str
    kind: str  # class, struct, enum, typedef, using
    code: str
    file_path: str
    line: int

    def __str__(self) -> str:
        return f"{self.kind} {self.name} ({self.file_path}:{self.line})"


@dataclass
class MacroDefinition:
    """Macro definition information."""
    name: str
    definition: str
    file_path: str
    line: int
    is_function_like: bool = False

    def __str__(self) -> str:
        macro_type = "function-like" if self.is_function_like else "object-like"
        return f"#define {self.name} ({macro_type}, {self.file_path}:{self.line})"


@dataclass
class RuleInfo:
    """Rule information from the rules database."""
    rule_id: str
    title: str
    category: str  # Required, Advisory, etc.
    rationale: str
    false_positive_hints: List[str] = field(default_factory=list)

    def to_prompt_text(self) -> str:
        """Convert to text for LLM prompt.

        Returns:
            Formatted rule information string
        """
        hints_text = ""
        if self.false_positive_hints:
            hints_text = "\n**誤検知の可能性があるケース**:\n"
            hints_text += "\n".join(f"- {hint}" for hint in self.false_positive_hints)

        return f"""**ルールID**: {self.rule_id}
**タイトル**: {self.title}
**カテゴリ**: {self.category}
**根拠**: {self.rationale}{hints_text}"""


@dataclass
class AnalysisContext:
    """Analysis context for LLM classification.

    Contains all information needed to classify a finding.
    """
    target_function: FunctionInfo
    finding_line: int  # Absolute line number of the finding

    # Rule information
    rule_info: Optional[RuleInfo] = None

    # Phase 2 additional context
    caller_functions: List[FunctionInfo] = field(default_factory=list)
    related_types: List[TypeDefinition] = field(default_factory=list)
    related_macros: List[MacroDefinition] = field(default_factory=list)

    def relative_finding_line(self) -> int:
        """Get the finding line relative to the function start.

        Returns:
            Line number within the function (1-indexed)
        """
        return self.finding_line - self.target_function.start_line + 1

    def estimate_tokens(self) -> int:
        """Estimate the number of tokens in this context.

        Uses rough estimate of 1 token per 3 characters for mixed Japanese/code.

        Returns:
            Estimated token count
        """
        total_chars = len(self.target_function.code)
        total_chars += sum(len(f.code) for f in self.caller_functions)
        total_chars += sum(len(t.code) for t in self.related_types)
        total_chars += sum(len(m.definition) for m in self.related_macros)

        if self.rule_info:
            total_chars += len(self.rule_info.to_prompt_text())

        return total_chars // 3

    def has_additional_context(self) -> bool:
        """Check if Phase 2 context is available.

        Returns:
            True if any additional context is present
        """
        return bool(
            self.caller_functions or
            self.related_types or
            self.related_macros
        )
