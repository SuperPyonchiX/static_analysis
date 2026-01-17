"""libclangを使用したC++関数の呼び出し元追跡。"""

from typing import List, Set, Optional
import os
import logging

from ..models.context import FunctionInfo
from .clang_analyzer import ClangAnalyzer

logger = logging.getLogger(__name__)


class CallerTracker:
    """ソースファイル全体で関数の呼び出し元を追跡する。"""

    def __init__(
        self,
        clang_analyzer: ClangAnalyzer,
        source_files: List[str]
    ):
        """呼び出し元追跡器を初期化する。

        Args:
            clang_analyzer: ClangAnalyzerインスタンス
            source_files: 検索対象のソースファイルリスト
        """
        self.analyzer = clang_analyzer
        self.source_files = [os.path.normpath(f) for f in source_files]
        self._ci = clang_analyzer.ci

    def find_callers(
        self,
        function_name: str,
        file_path: str,
        max_depth: int = 1,
        max_callers: int = 3
    ) -> List[FunctionInfo]:
        """指定された関数を呼び出す関数を検索する。

        Args:
            function_name: 呼び出し元を検索する関数名
            file_path: 関数が定義されているファイル
            max_depth: 追跡する最大呼び出し深度（デフォルト: 1）
            max_callers: 返す呼び出し元の最大数

        Returns:
            呼び出し元関数のFunctionInfoリスト
        """
        callers: List[FunctionInfo] = []
        visited: Set[str] = set()

        self._find_callers_recursive(
            function_name,
            file_path,
            callers,
            visited,
            current_depth=0,
            max_depth=max_depth,
            max_callers=max_callers
        )

        return callers[:max_callers]

    def _find_callers_recursive(
        self,
        function_name: str,
        file_path: str,
        callers: List[FunctionInfo],
        visited: Set[str],
        current_depth: int,
        max_depth: int,
        max_callers: int
    ) -> None:
        """再帰的に呼び出し元を検索する。

        Args:
            function_name: 対象関数名
            file_path: 対象ファイルパス
            callers: 呼び出し元を追加するリスト
            visited: 訪問済み関数キーのセット
            current_depth: 現在の再帰深度
            max_depth: 最大深度
            max_callers: 検索する呼び出し元の最大数
        """
        if current_depth >= max_depth or len(callers) >= max_callers:
            return

        # 各ソースファイルで検索
        for src_file in self.source_files:
            if len(callers) >= max_callers:
                break

            try:
                tu = self.analyzer.get_translation_unit_full(src_file)
                self._search_calls_in_tu(
                    tu.cursor,
                    function_name,
                    src_file,
                    callers,
                    visited,
                    max_callers
                )
            except Exception as e:
                logger.debug(f"Failed to search {src_file}: {e}")
                continue

    def _search_calls_in_tu(
        self,
        cursor,
        target_name: str,
        file_path: str,
        callers: List[FunctionInfo],
        visited: Set[str],
        max_callers: int
    ) -> None:
        """TranslationUnit内で関数呼び出しを検索する。

        Args:
            cursor: ルートカーソル
            target_name: 呼び出しを検索する関数名
            file_path: 現在のファイルパス
            callers: 呼び出し元を追加するリスト
            visited: 訪問済み関数キーのセット
            max_callers: 検索する呼び出し元の最大数
        """
        CursorKind = self._ci.CursorKind

        function_kinds = {
            CursorKind.FUNCTION_DECL,
            CursorKind.CXX_METHOD,
            CursorKind.CONSTRUCTOR,
            CursorKind.DESTRUCTOR,
        }

        def traverse(node, enclosing_func):
            nonlocal callers

            if len(callers) >= max_callers:
                return

            # 他のファイルのノードをスキップ
            if node.location.file:
                node_file = os.path.normpath(node.location.file.name)
                if node_file != os.path.normpath(file_path):
                    return

            # 包含する関数を追跡
            if node.kind in function_kinds and node.is_definition():
                enclosing_func = node

            # 関数呼び出しをチェック
            if node.kind == CursorKind.CALL_EXPR:
                called_name = node.spelling

                if called_name == target_name and enclosing_func:
                    func_key = f"{file_path}:{enclosing_func.spelling}"

                    if func_key not in visited:
                        visited.add(func_key)

                        # 呼び出し元関数の情報を抽出
                        func_info = self._extract_function_info(
                            enclosing_func, file_path
                        )
                        if func_info:
                            callers.append(func_info)
                            logger.debug(
                                f"Found caller: {func_info.name} -> {target_name}"
                            )

            # 子ノードを走査
            for child in node.get_children():
                traverse(child, enclosing_func)

        traverse(cursor, None)

    def _extract_function_info(
        self,
        cursor,
        file_path: str
    ) -> Optional[FunctionInfo]:
        """カーソルからFunctionInfoを抽出する。

        Args:
            cursor: 関数カーソル
            file_path: ソースファイルパス

        Returns:
            FunctionInfo、エラー時はNone
        """
        try:
            extent = cursor.extent
            start_line = extent.start.line
            end_line = extent.end.line

            # ソースコードを読み込む
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            code = "".join(lines[start_line - 1:end_line])

            return FunctionInfo(
                name=cursor.spelling,
                file_path=file_path,
                start_line=start_line,
                end_line=end_line,
                code=code,
                signature=cursor.displayname
            )

        except Exception as e:
            logger.warning(f"Failed to extract function info: {e}")
            return None

    def find_call_chain(
        self,
        function_name: str,
        file_path: str,
        max_depth: int = 3
    ) -> List[List[FunctionInfo]]:
        """関数に至る呼び出しチェーンを検索する。

        Args:
            function_name: 対象関数名
            file_path: 関数が定義されているファイル
            max_depth: チェーンの最大深度

        Returns:
            呼び出しチェーンのリスト（各チェーンはFunctionInfoのリスト）
        """
        chains: List[List[FunctionInfo]] = []
        visited: Set[str] = set()

        def build_chain(
            func_name: str,
            current_chain: List[FunctionInfo],
            depth: int
        ):
            if depth >= max_depth or len(chains) >= 10:
                return

            callers = self.find_callers(func_name, file_path, max_depth=1, max_callers=5)

            if not callers:
                # チェーンの終端
                if current_chain:
                    chains.append(list(current_chain))
                return

            for caller in callers:
                caller_key = f"{caller.file_path}:{caller.name}"
                if caller_key in visited:
                    continue

                visited.add(caller_key)
                current_chain.append(caller)

                # この呼び出し元の呼び出し元を再帰的に検索
                build_chain(caller.name, current_chain, depth + 1)

                current_chain.pop()
                visited.discard(caller_key)

        build_chain(function_name, [], 0)
        return chains
