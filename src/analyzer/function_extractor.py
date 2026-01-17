"""libclangを使用したC++ソースファイルからの関数抽出。"""

from typing import Optional, Tuple, Set
import logging

from ..models.context import FunctionInfo
from .clang_analyzer import ClangAnalyzer

logger = logging.getLogger(__name__)


class FunctionExtractor:
    """C++ソースファイルから関数情報を抽出する。"""

    # 関数定義を表すカーソル種別
    FUNCTION_KINDS: Set[str] = {
        "FUNCTION_DECL",
        "CXX_METHOD",
        "CONSTRUCTOR",
        "DESTRUCTOR",
        "FUNCTION_TEMPLATE",
        "LAMBDA_EXPR",
    }

    def __init__(self, clang_analyzer: ClangAnalyzer):
        """関数抽出器を初期化する。

        Args:
            clang_analyzer: パース用のClangAnalyzerインスタンス
        """
        self.analyzer = clang_analyzer
        self._ci = clang_analyzer.ci

    def extract_function_at_line(
        self,
        file_path: str,
        line: int
    ) -> Optional[FunctionInfo]:
        """特定の行を含む関数を抽出する。

        Args:
            file_path: ソースファイルのパス
            line: 対象行番号（1始まり）

        Returns:
            FunctionInfo、関数が見つからない場合はNone
        """
        try:
            tu = self.analyzer.get_translation_unit_full(file_path)
            function_cursor = self._find_enclosing_function(
                tu.cursor, file_path, line
            )

            if function_cursor is None:
                logger.debug(f"No function found at {file_path}:{line}")
                return None

            return self._cursor_to_function_info(function_cursor, file_path)

        except Exception as e:
            logger.warning(f"Failed to extract function at {file_path}:{line}: {e}")
            return None

    def _find_enclosing_function(
        self,
        cursor,
        file_path: str,
        target_line: int
    ):
        """対象行を含む関数カーソルを検索する。

        Args:
            cursor: 検索開始のルートカーソル
            file_path: ソースファイルのパス
            target_line: 対象行番号

        Returns:
            関数カーソル、またはNone
        """
        result = None
        CursorKind = self._ci.CursorKind

        # 関数カーソル種別のセットを構築
        function_kinds = {
            CursorKind.FUNCTION_DECL,
            CursorKind.CXX_METHOD,
            CursorKind.CONSTRUCTOR,
            CursorKind.DESTRUCTOR,
            CursorKind.FUNCTION_TEMPLATE,
        }

        def traverse(node):
            nonlocal result

            # 他のファイルのノードをスキップ
            if node.location.file:
                node_file = node.location.file.name
                # 比較のためにパスを正規化
                import os
                if os.path.normpath(node_file) != os.path.normpath(file_path):
                    return

            # 対象行を含む関数かどうかをチェック
            if node.kind in function_kinds:
                extent = node.extent
                if extent.start.line <= target_line <= extent.end.line:
                    # 定義（本体がある）かどうかをチェック
                    if node.is_definition():
                        # 内部関数（ラムダ、ネストされた関数）を探す
                        inner = self._find_enclosing_function(
                            node, file_path, target_line
                        )
                        result = inner if inner else node
                        return

            # ラムダ式もチェック
            if node.kind == CursorKind.LAMBDA_EXPR:
                extent = node.extent
                if extent.start.line <= target_line <= extent.end.line:
                    result = node
                    return

            # 子ノードを走査
            for child in node.get_children():
                traverse(child)
                if result:
                    return

        traverse(cursor)
        return result

    def _cursor_to_function_info(
        self,
        cursor,
        file_path: str
    ) -> FunctionInfo:
        """カーソルをFunctionInfoに変換する。

        Args:
            cursor: 関数カーソル
            file_path: ソースファイルのパス

        Returns:
            FunctionInfoインスタンス
        """
        extent = cursor.extent
        start_line = extent.start.line
        end_line = extent.end.line

        # ソースコードを読み込む
        code = self._read_source_range(file_path, start_line, end_line)

        # パラメータを抽出
        parameters = []
        CursorKind = self._ci.CursorKind
        for child in cursor.get_children():
            if child.kind == CursorKind.PARM_DECL:
                param_type = child.type.spelling
                param_name = child.spelling
                if param_name:
                    parameters.append(f"{param_type} {param_name}")
                else:
                    parameters.append(param_type)

        # 戻り値の型を取得
        return_type = None
        if hasattr(cursor, "result_type") and cursor.result_type:
            return_type = cursor.result_type.spelling

        return FunctionInfo(
            name=cursor.spelling or "<lambda>",
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            code=code,
            signature=cursor.displayname,
            return_type=return_type,
            parameters=parameters
        )

    def _read_source_range(
        self,
        file_path: str,
        start_line: int,
        end_line: int
    ) -> str:
        """ファイルの範囲からソースコードを読み込む。

        Args:
            file_path: ソースファイルのパス
            start_line: 開始行（1始まり）
            end_line: 終了行（1始まり）

        Returns:
            ソースコード文字列
        """
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            # 0始まりに変換
            selected_lines = lines[start_line - 1:end_line]
            return "".join(selected_lines)

        except Exception as e:
            logger.warning(f"Failed to read {file_path}:{start_line}-{end_line}: {e}")
            return ""

    def extract_function_with_context(
        self,
        file_path: str,
        line: int,
        context_lines: int = 20
    ) -> Tuple[Optional[FunctionInfo], str]:
        """関数を抽出するか、見つからない場合はコンテキスト行にフォールバックする。

        関数が見つからない場合は、周辺の行をコンテキストとして返す。

        Args:
            file_path: ソースファイルのパス
            line: 対象行番号
            context_lines: 関数が見つからない場合のコンテキスト行数

        Returns:
            (FunctionInfoまたはNone, コンテキストコード)のタプル
        """
        func_info = self.extract_function_at_line(file_path, line)

        if func_info:
            return func_info, func_info.code

        # 関数が見つからない場合、コンテキスト行を読み込む
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            start = max(0, line - context_lines - 1)
            end = min(len(lines), line + context_lines)

            context_code = "".join(lines[start:end])

            # コンテキスト用の疑似FunctionInfoを作成
            pseudo_func = FunctionInfo(
                name="<context>",
                file_path=file_path,
                start_line=start + 1,
                end_line=end,
                code=context_code
            )

            return pseudo_func, context_code

        except Exception as e:
            logger.warning(f"Failed to read context from {file_path}: {e}")
            return None, ""

    def get_all_functions(self, file_path: str) -> list:
        """ファイル内の全関数定義を取得する。

        Args:
            file_path: ソースファイルのパス

        Returns:
            全関数のFunctionInfoリスト
        """
        try:
            tu = self.analyzer.get_translation_unit_full(file_path)
        except Exception as e:
            logger.warning(f"Failed to parse {file_path}: {e}")
            return []

        functions = []
        CursorKind = self._ci.CursorKind

        function_kinds = {
            CursorKind.FUNCTION_DECL,
            CursorKind.CXX_METHOD,
            CursorKind.CONSTRUCTOR,
            CursorKind.DESTRUCTOR,
        }

        def traverse(node):
            import os
            # 他のファイルのノードをスキップ
            if node.location.file:
                node_file = node.location.file.name
                if os.path.normpath(node_file) != os.path.normpath(file_path):
                    return

            if node.kind in function_kinds and node.is_definition():
                func_info = self._cursor_to_function_info(node, file_path)
                functions.append(func_info)

            for child in node.get_children():
                traverse(child)

        traverse(tu.cursor)
        return functions
