"""LLM解析用のコンテキストモデル。"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict


@dataclass
class FunctionInfo:
    """ソースコードから抽出した関数情報。"""
    name: str
    file_path: str
    start_line: int
    end_line: int
    code: str
    signature: Optional[str] = None
    return_type: Optional[str] = None
    parameters: List[str] = field(default_factory=list)

    def line_count(self) -> int:
        """関数の行数を取得する。"""
        return self.end_line - self.start_line + 1

    def __str__(self) -> str:
        return f"{self.name} ({self.file_path}:{self.start_line}-{self.end_line})"


@dataclass
class TypeDefinition:
    """型定義情報（class, struct, enum, typedef）。"""
    name: str
    kind: str  # class, struct, enum, typedef, using
    code: str
    file_path: str
    line: int

    def __str__(self) -> str:
        return f"{self.kind} {self.name} ({self.file_path}:{self.line})"


@dataclass
class MacroDefinition:
    """マクロ定義情報。"""
    name: str
    definition: str
    file_path: str
    line: int
    is_function_like: bool = False

    def __str__(self) -> str:
        macro_type = "関数形式" if self.is_function_like else "オブジェクト形式"
        return f"#define {self.name} ({macro_type}, {self.file_path}:{self.line})"


@dataclass
class RuleInfo:
    """ルールデータベースからのルール情報。"""
    rule_id: str
    title: str
    category: str  # Required, Advisory など
    rationale: str
    false_positive_hints: List[str] = field(default_factory=list)

    def to_prompt_text(self) -> str:
        """LLMプロンプト用のテキストに変換する。

        Returns:
            フォーマット済みのルール情報文字列
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
    """LLM分類用の解析コンテキスト。

    指摘を分類するために必要な全情報を含む。
    """
    target_function: FunctionInfo
    finding_line: int  # 指摘の絶対行番号

    # ルール情報
    rule_info: Optional[RuleInfo] = None

    # Phase 2 追加コンテキスト
    caller_functions: List[FunctionInfo] = field(default_factory=list)
    related_types: List[TypeDefinition] = field(default_factory=list)
    related_macros: List[MacroDefinition] = field(default_factory=list)

    def relative_finding_line(self) -> int:
        """関数開始位置からの相対的な指摘行を取得する。

        Returns:
            関数内での行番号（1始まり）
        """
        return self.finding_line - self.target_function.start_line + 1

    def estimate_tokens(self) -> int:
        """このコンテキストのトークン数を推定する。

        日本語/コード混在で1トークン≒3文字として概算。

        Returns:
            推定トークン数
        """
        total_chars = len(self.target_function.code)
        total_chars += sum(len(f.code) for f in self.caller_functions)
        total_chars += sum(len(t.code) for t in self.related_types)
        total_chars += sum(len(m.definition) for m in self.related_macros)

        if self.rule_info:
            total_chars += len(self.rule_info.to_prompt_text())

        return total_chars // 3

    def has_additional_context(self) -> bool:
        """Phase 2コンテキストが存在するかを確認する。

        Returns:
            追加コンテキストが存在する場合True
        """
        return bool(
            self.caller_functions or
            self.related_types or
            self.related_macros
        )
