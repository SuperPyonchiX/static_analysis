"""Caller tracking for C++ functions using libclang."""

from typing import List, Set, Optional
import os
import logging

from ..models.context import FunctionInfo
from .clang_analyzer import ClangAnalyzer

logger = logging.getLogger(__name__)


class CallerTracker:
    """Track function callers across source files."""

    def __init__(
        self,
        clang_analyzer: ClangAnalyzer,
        source_files: List[str]
    ):
        """Initialize the caller tracker.

        Args:
            clang_analyzer: ClangAnalyzer instance
            source_files: List of source files to search
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
        """Find functions that call the specified function.

        Args:
            function_name: Name of the function to find callers for
            file_path: File where the function is defined
            max_depth: Maximum call depth to track (default: 1)
            max_callers: Maximum number of callers to return

        Returns:
            List of FunctionInfo for caller functions
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
        """Recursively find callers.

        Args:
            function_name: Target function name
            file_path: Target file path
            callers: List to append callers to
            visited: Set of visited function keys
            current_depth: Current recursion depth
            max_depth: Maximum depth
            max_callers: Maximum callers to find
        """
        if current_depth >= max_depth or len(callers) >= max_callers:
            return

        # Search in each source file
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
        """Search for function calls in a TranslationUnit.

        Args:
            cursor: Root cursor
            target_name: Function name to find calls to
            file_path: Current file path
            callers: List to append callers to
            visited: Set of visited function keys
            max_callers: Maximum callers to find
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

            # Skip nodes from other files
            if node.location.file:
                node_file = os.path.normpath(node.location.file.name)
                if node_file != os.path.normpath(file_path):
                    return

            # Track enclosing function
            if node.kind in function_kinds and node.is_definition():
                enclosing_func = node

            # Check for function calls
            if node.kind == CursorKind.CALL_EXPR:
                called_name = node.spelling

                if called_name == target_name and enclosing_func:
                    func_key = f"{file_path}:{enclosing_func.spelling}"

                    if func_key not in visited:
                        visited.add(func_key)

                        # Extract caller function info
                        func_info = self._extract_function_info(
                            enclosing_func, file_path
                        )
                        if func_info:
                            callers.append(func_info)
                            logger.debug(
                                f"Found caller: {func_info.name} -> {target_name}"
                            )

            # Traverse children
            for child in node.get_children():
                traverse(child, enclosing_func)

        traverse(cursor, None)

    def _extract_function_info(
        self,
        cursor,
        file_path: str
    ) -> Optional[FunctionInfo]:
        """Extract FunctionInfo from a cursor.

        Args:
            cursor: Function cursor
            file_path: Source file path

        Returns:
            FunctionInfo or None on error
        """
        try:
            extent = cursor.extent
            start_line = extent.start.line
            end_line = extent.end.line

            # Read source code
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
        """Find call chains leading to a function.

        Args:
            function_name: Target function name
            file_path: File where the function is defined
            max_depth: Maximum chain depth

        Returns:
            List of call chains (each chain is a list of FunctionInfo)
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
                # End of chain
                if current_chain:
                    chains.append(list(current_chain))
                return

            for caller in callers:
                caller_key = f"{caller.file_path}:{caller.name}"
                if caller_key in visited:
                    continue

                visited.add(caller_key)
                current_chain.append(caller)

                # Recursively find callers of this caller
                build_chain(caller.name, current_chain, depth + 1)

                current_chain.pop()
                visited.discard(caller_key)

        build_chain(function_name, [], 0)
        return chains
