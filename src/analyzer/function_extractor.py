"""Function extraction from C++ source files using libclang."""

from typing import Optional, Tuple, Set
import logging

from ..models.context import FunctionInfo
from .clang_analyzer import ClangAnalyzer

logger = logging.getLogger(__name__)


class FunctionExtractor:
    """Extract function information from C++ source files."""

    # Cursor kinds that represent function definitions
    FUNCTION_KINDS: Set[str] = {
        "FUNCTION_DECL",
        "CXX_METHOD",
        "CONSTRUCTOR",
        "DESTRUCTOR",
        "FUNCTION_TEMPLATE",
        "LAMBDA_EXPR",
    }

    def __init__(self, clang_analyzer: ClangAnalyzer):
        """Initialize the function extractor.

        Args:
            clang_analyzer: ClangAnalyzer instance for parsing
        """
        self.analyzer = clang_analyzer
        self._ci = clang_analyzer.ci

    def extract_function_at_line(
        self,
        file_path: str,
        line: int
    ) -> Optional[FunctionInfo]:
        """Extract the function containing a specific line.

        Args:
            file_path: Path to the source file
            line: Target line number (1-indexed)

        Returns:
            FunctionInfo or None if no function found
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
        """Find the function cursor that contains the target line.

        Args:
            cursor: Root cursor to search from
            file_path: Path to the source file
            target_line: Target line number

        Returns:
            Function cursor or None
        """
        result = None
        CursorKind = self._ci.CursorKind

        # Build set of function cursor kinds
        function_kinds = {
            CursorKind.FUNCTION_DECL,
            CursorKind.CXX_METHOD,
            CursorKind.CONSTRUCTOR,
            CursorKind.DESTRUCTOR,
            CursorKind.FUNCTION_TEMPLATE,
        }

        def traverse(node):
            nonlocal result

            # Skip nodes from other files
            if node.location.file:
                node_file = node.location.file.name
                # Normalize paths for comparison
                import os
                if os.path.normpath(node_file) != os.path.normpath(file_path):
                    return

            # Check if this is a function containing the target line
            if node.kind in function_kinds:
                extent = node.extent
                if extent.start.line <= target_line <= extent.end.line:
                    # Check if this is a definition (has a body)
                    if node.is_definition():
                        # Look for inner functions (lambdas, nested functions)
                        inner = self._find_enclosing_function(
                            node, file_path, target_line
                        )
                        result = inner if inner else node
                        return

            # Also check for lambda expressions
            if node.kind == CursorKind.LAMBDA_EXPR:
                extent = node.extent
                if extent.start.line <= target_line <= extent.end.line:
                    result = node
                    return

            # Traverse children
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
        """Convert a cursor to FunctionInfo.

        Args:
            cursor: Function cursor
            file_path: Source file path

        Returns:
            FunctionInfo instance
        """
        extent = cursor.extent
        start_line = extent.start.line
        end_line = extent.end.line

        # Read source code
        code = self._read_source_range(file_path, start_line, end_line)

        # Extract parameters
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

        # Get return type
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
        """Read source code from a file range.

        Args:
            file_path: Path to the source file
            start_line: Start line (1-indexed)
            end_line: End line (1-indexed)

        Returns:
            Source code string
        """
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            # Convert to 0-indexed
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
        """Extract function or fallback to context lines.

        If no function is found, returns surrounding lines as context.

        Args:
            file_path: Path to the source file
            line: Target line number
            context_lines: Number of context lines if no function found

        Returns:
            Tuple of (FunctionInfo or None, context code)
        """
        func_info = self.extract_function_at_line(file_path, line)

        if func_info:
            return func_info, func_info.code

        # No function found, read context lines
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            start = max(0, line - context_lines - 1)
            end = min(len(lines), line + context_lines)

            context_code = "".join(lines[start:end])

            # Create a pseudo FunctionInfo for context
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
        """Get all function definitions in a file.

        Args:
            file_path: Path to the source file

        Returns:
            List of FunctionInfo for all functions
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
            # Skip nodes from other files
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
