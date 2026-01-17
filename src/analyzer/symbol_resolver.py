"""Symbol resolution for types and macros in C++ source files."""

from typing import List, Set, Optional
import re
import os
import logging

from ..models.context import TypeDefinition, MacroDefinition
from .clang_analyzer import ClangAnalyzer

logger = logging.getLogger(__name__)


class SymbolResolver:
    """Resolve type definitions and macros from C++ source files."""

    # Standard library types to exclude
    STD_TYPES: Set[str] = {
        "String", "Vector", "Map", "Set", "List", "Array",
        "int8_t", "int16_t", "int32_t", "int64_t",
        "uint8_t", "uint16_t", "uint32_t", "uint64_t",
        "size_t", "ptrdiff_t", "nullptr_t", "bool", "char",
        "short", "int", "long", "float", "double", "void",
        "string", "vector", "map", "set", "list", "array",
    }

    # Common macro names to exclude
    COMMON_MACROS: Set[str] = {
        "TRUE", "FALSE", "NULL", "EOF", "EXIT_SUCCESS", "EXIT_FAILURE",
        "UINT8_MAX", "UINT16_MAX", "UINT32_MAX", "UINT64_MAX",
        "INT8_MIN", "INT16_MIN", "INT32_MIN", "INT64_MIN",
        "INT8_MAX", "INT16_MAX", "INT32_MAX", "INT64_MAX",
        "SIZE_MAX", "PTRDIFF_MAX", "PTRDIFF_MIN",
    }

    def __init__(self, clang_analyzer: ClangAnalyzer):
        """Initialize the symbol resolver.

        Args:
            clang_analyzer: ClangAnalyzer instance
        """
        self.analyzer = clang_analyzer
        self._ci = clang_analyzer.ci

    def find_types_in_function(
        self,
        function_code: str,
        file_path: str,
        max_types: int = 10
    ) -> List[TypeDefinition]:
        """Find type definitions used in a function.

        Args:
            function_code: Function source code
            file_path: Source file path
            max_types: Maximum number of types to return

        Returns:
            List of TypeDefinition objects
        """
        # Extract type name candidates from code
        type_candidates = self._extract_type_names(function_code)

        if not type_candidates:
            return []

        try:
            tu = self.analyzer.get_translation_unit(file_path)
        except Exception as e:
            logger.warning(f"Failed to parse {file_path}: {e}")
            return []

        type_definitions: List[TypeDefinition] = []
        found_types: Set[str] = set()

        CursorKind = self._ci.CursorKind

        type_cursor_kinds = {
            CursorKind.CLASS_DECL,
            CursorKind.STRUCT_DECL,
            CursorKind.ENUM_DECL,
            CursorKind.TYPEDEF_DECL,
            CursorKind.TYPE_ALIAS_DECL,
            CursorKind.CLASS_TEMPLATE,
        }

        def find_type_def(cursor):
            if len(type_definitions) >= max_types:
                return

            # Check if this cursor matches a type candidate
            if (cursor.spelling in type_candidates and
                cursor.spelling not in found_types and
                cursor.kind in type_cursor_kinds):

                # Only get definitions
                if cursor.is_definition():
                    type_def = self._cursor_to_type_definition(cursor)
                    if type_def:
                        type_definitions.append(type_def)
                        found_types.add(cursor.spelling)
                        logger.debug(f"Found type: {cursor.spelling}")

            for child in cursor.get_children():
                find_type_def(child)

        find_type_def(tu.cursor)

        return type_definitions

    def _extract_type_names(self, code: str) -> Set[str]:
        """Extract potential type names from code.

        Args:
            code: Source code to analyze

        Returns:
            Set of potential type names
        """
        # Pattern for type names:
        # - Capital letter followed by alphanumerics/underscores
        # - lowercase followed by lowercase/digits and ending with _t
        pattern = r'\b([A-Z][A-Za-z0-9_]*|[a-z][a-z0-9_]*_t)\b'
        matches = re.findall(pattern, code)

        # Filter out standard types
        result = {m for m in matches if m not in self.STD_TYPES}

        return result

    def _cursor_to_type_definition(
        self,
        cursor
    ) -> Optional[TypeDefinition]:
        """Convert a cursor to TypeDefinition.

        Args:
            cursor: Type cursor

        Returns:
            TypeDefinition or None on error
        """
        try:
            extent = cursor.extent

            if not cursor.location.file:
                return None

            file_path = cursor.location.file.name

            # Read type definition code
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            code = "".join(lines[extent.start.line - 1:extent.end.line])

            # Map cursor kind to type kind string
            CursorKind = self._ci.CursorKind
            kind_map = {
                CursorKind.CLASS_DECL: "class",
                CursorKind.STRUCT_DECL: "struct",
                CursorKind.ENUM_DECL: "enum",
                CursorKind.TYPEDEF_DECL: "typedef",
                CursorKind.TYPE_ALIAS_DECL: "using",
                CursorKind.CLASS_TEMPLATE: "template class",
            }

            return TypeDefinition(
                name=cursor.spelling,
                kind=kind_map.get(cursor.kind, "unknown"),
                code=code,
                file_path=file_path,
                line=cursor.location.line
            )

        except Exception as e:
            logger.warning(f"Failed to extract type definition: {e}")
            return None

    def find_macros_in_code(
        self,
        code: str,
        file_path: str,
        max_macros: int = 10
    ) -> List[MacroDefinition]:
        """Find macro definitions used in code.

        Args:
            code: Source code to analyze
            file_path: Source file path
            max_macros: Maximum number of macros to return

        Returns:
            List of MacroDefinition objects
        """
        # Extract macro name candidates
        macro_candidates = self._extract_macro_names(code)

        if not macro_candidates:
            return []

        try:
            tu = self.analyzer.get_translation_unit(file_path)
        except Exception as e:
            logger.warning(f"Failed to parse {file_path}: {e}")
            return []

        macros: List[MacroDefinition] = []
        found_macros: Set[str] = set()

        CursorKind = self._ci.CursorKind

        # Iterate through macro definitions
        for cursor in tu.cursor.get_children():
            if len(macros) >= max_macros:
                break

            if cursor.kind == CursorKind.MACRO_DEFINITION:
                if (cursor.spelling in macro_candidates and
                    cursor.spelling not in found_macros):

                    macro_def = self._cursor_to_macro_definition(cursor)
                    if macro_def:
                        macros.append(macro_def)
                        found_macros.add(cursor.spelling)
                        logger.debug(f"Found macro: {cursor.spelling}")

        return macros

    def _extract_macro_names(self, code: str) -> Set[str]:
        """Extract potential macro names from code.

        Args:
            code: Source code to analyze

        Returns:
            Set of potential macro names
        """
        # Pattern for macro names: uppercase letters and underscores
        pattern = r'\b([A-Z][A-Z0-9_]+)\b'
        matches = re.findall(pattern, code)

        # Filter out common macros and short names
        result = {
            m for m in matches
            if m not in self.COMMON_MACROS and len(m) > 2
        }

        return result

    def _cursor_to_macro_definition(
        self,
        cursor
    ) -> Optional[MacroDefinition]:
        """Convert a cursor to MacroDefinition.

        Args:
            cursor: Macro cursor

        Returns:
            MacroDefinition or None on error
        """
        try:
            tokens = list(cursor.get_tokens())
            if not tokens:
                return None

            # Reconstruct definition from tokens
            definition = " ".join(t.spelling for t in tokens)

            # Check if function-like macro
            is_function_like = len(tokens) > 1 and tokens[1].spelling == "("

            file_path = ""
            if cursor.location.file:
                file_path = cursor.location.file.name

            return MacroDefinition(
                name=cursor.spelling,
                definition=definition,
                file_path=file_path,
                line=cursor.location.line,
                is_function_like=is_function_like
            )

        except Exception as e:
            logger.warning(f"Failed to extract macro definition: {e}")
            return None

    def find_included_headers(self, file_path: str) -> List[str]:
        """Find all headers included by a file.

        Args:
            file_path: Source file path

        Returns:
            List of included header paths
        """
        try:
            tu = self.analyzer.get_translation_unit(file_path)
        except Exception as e:
            logger.warning(f"Failed to parse {file_path}: {e}")
            return []

        headers = []
        CursorKind = self._ci.CursorKind

        for cursor in tu.cursor.get_children():
            if cursor.kind == CursorKind.INCLUSION_DIRECTIVE:
                included = cursor.get_included_file()
                if included:
                    headers.append(included.name)

        return headers
