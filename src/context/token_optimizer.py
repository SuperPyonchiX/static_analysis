"""LLMコンテキスト用のトークン最適化。"""

from typing import Optional, List
import logging

from ..models.context import AnalysisContext, FunctionInfo

logger = logging.getLogger(__name__)


class TokenOptimizer:
    """トークン制限内に収まるようにコンテキストを最適化する。"""

    # GPT-5-miniのトークン制限（安全マージン込み）
    DEFAULT_MAX_TOKENS = 250000

    # システムプロンプトとフォーマット用のベーストークン
    BASE_TOKENS = 2000

    # トークンあたりの平均文字数（日本語/コード混在）
    CHARS_PER_TOKEN = 3

    def __init__(self, max_tokens: int = DEFAULT_MAX_TOKENS):
        """トークン最適化器を初期化する。

        Args:
            max_tokens: 許容される最大入力トークン数
        """
        self.max_tokens = max_tokens

    def optimize_context(self, context: AnalysisContext) -> AnalysisContext:
        """トークン制限内に収まるようにコンテキストを最適化する。

        Args:
            context: 元の解析コンテキスト

        Returns:
            最適化された解析コンテキスト
        """
        available_tokens = self.max_tokens - self.BASE_TOKENS

        # バジェット配分を計算
        # 優先度: 対象関数 > 呼び出し元 > 型 > マクロ
        target_budget = int(available_tokens * 0.6)
        caller_budget = int(available_tokens * 0.25)
        type_budget = int(available_tokens * 0.10)
        macro_budget = int(available_tokens * 0.05)

        # 対象関数を最適化
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

        # 実際の対象使用量に基づいて残りのバジェットを調整
        remaining = available_tokens - target_tokens
        caller_budget = int(remaining * 0.5)
        type_budget = int(remaining * 0.3)
        macro_budget = int(remaining * 0.2)

        # 呼び出し元を最適化
        if context.caller_functions:
            context.caller_functions = self._optimize_functions(
                context.caller_functions,
                caller_budget
            )

        # 型を最適化
        if context.related_types:
            context.related_types = self._optimize_items(
                context.related_types,
                type_budget,
                key=lambda t: len(t.code)
            )

        # マクロを最適化
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
        """テキストのトークン数を推定する。

        Args:
            text: 推定するテキスト

        Returns:
            推定トークン数
        """
        return len(text) // self.CHARS_PER_TOKEN

    def _truncate_function(
        self,
        func: FunctionInfo,
        focus_line: int,
        max_tokens: int
    ) -> FunctionInfo:
        """トークンバジェットに収まるように関数を切り詰める。

        指摘行をコンテキスト内に保持する。

        Args:
            func: 切り詰める関数
            focus_line: 表示を維持する行
            max_tokens: 許容される最大トークン数

        Returns:
            切り詰められたFunctionInfo
        """
        lines = func.code.split("\n")
        max_chars = max_tokens * self.CHARS_PER_TOKEN

        # 相対的な行位置を計算
        relative_line = focus_line - func.start_line

        # フォーカス行から外側に展開
        result_lines = []
        current_chars = 0

        # 中心範囲を決定
        center_start = max(0, relative_line - 50)
        center_end = min(len(lines), relative_line + 50)

        for i in range(center_start, center_end):
            line = lines[i]
            if current_chars + len(line) + 1 > max_chars:
                break
            result_lines.append(line)
            current_chars += len(line) + 1

        # 切り詰めマーカーを追加
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
        """バジェットに収まるように関数リストを最適化する。

        Args:
            functions: 関数のリスト
            budget: トークンバジェット

        Returns:
            最適化された関数リスト
        """
        result = []
        used_tokens = 0

        for func in functions:
            tokens = self._estimate_tokens(func.code)

            if used_tokens + tokens <= budget:
                result.append(func)
                used_tokens += tokens
            else:
                # 切り詰めたバージョンを収めてみる
                remaining = budget - used_tokens
                if remaining > 100:  # 最小有用サイズ
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
        """呼び出し元関数を切り詰める。

        Args:
            func: 切り詰める関数
            max_tokens: 最大トークン数

        Returns:
            切り詰められた関数、小さすぎる場合はNone
        """
        if max_tokens < 50:
            return None

        lines = func.code.split("\n")
        max_chars = max_tokens * self.CHARS_PER_TOKEN

        result_lines = []
        current_chars = 0

        # 最初の行を保持（シグネチャと初期コード）
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
        """バジェットに収まるようにアイテムリストを最適化する。

        小さいアイテムを優先する。

        Args:
            items: アイテムのリスト
            budget: トークンバジェット
            key: アイテムのサイズを取得する関数

        Returns:
            最適化されたリスト
        """
        # サイズでソート（小さいものが先）
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
        """プロンプト全体のトークン数を推定する。

        Args:
            system_prompt: システムプロンプト
            user_prompt: ユーザープロンプト

        Returns:
            推定トークン数
        """
        total_chars = len(system_prompt) + len(user_prompt)
        return total_chars // self.CHARS_PER_TOKEN

    def will_fit(self, context: AnalysisContext) -> bool:
        """コンテキストが制限内に収まるかを確認する。

        Args:
            context: 解析コンテキスト

        Returns:
            コンテキストが収まる場合はTrue
        """
        estimated = context.estimate_tokens() + self.BASE_TOKENS
        return estimated <= self.max_tokens
