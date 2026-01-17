"""Data models for static analysis classification."""

from .finding import Finding, SourceLocation, Severity
from .classification import ClassificationResult, ClassificationType
from .context import (
    AnalysisContext,
    FunctionInfo,
    TypeDefinition,
    MacroDefinition,
    RuleInfo,
)

__all__ = [
    "Finding",
    "SourceLocation",
    "Severity",
    "ClassificationResult",
    "ClassificationType",
    "AnalysisContext",
    "FunctionInfo",
    "TypeDefinition",
    "MacroDefinition",
    "RuleInfo",
]
