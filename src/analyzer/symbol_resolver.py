"""C++ソースファイルの型およびマクロのシンボル解決。"""

from typing import List, Set, Optional
import re
import os
import logging

from ..models.context import TypeDefinition, MacroDefinition
from .clang_analyzer import ClangAnalyzer

logger = logging.getLogger(__name__)


class SymbolResolver:
    """C++ソースファイルから型定義とマクロを解決する。"""

    # 除外する標準ライブラリ型
    STD_TYPES: Set[str] = {
        "String", "Vector", "Map", "Set", "List", "Array",
        "int8_t", "int16_t", "int32_t", "int64_t",
        "uint8_t", "uint16_t", "uint32_t", "uint64_t",
        "size_t", "ptrdiff_t", "nullptr_t", "bool", "char",
        "short", "int", "long", "float", "double", "void",
        "string", "vector", "map", "set", "list", "array",
    }

    # 除外する一般的なマクロ名
    COMMON_MACROS: Set[str] = {
        "TRUE", "FALSE", "NULL", "EOF", "EXIT_SUCCESS", "EXIT_FAILURE",
        "UINT8_MAX", "UINT16_MAX", "UINT32_MAX", "UINT64_MAX",
        "INT8_MIN", "INT16_MIN", "INT32_MIN", "INT64_MIN",
        "INT8_MAX", "INT16_MAX", "INT32_MAX", "INT64_MAX",
        "SIZE_MAX", "PTRDIFF_MAX", "PTRDIFF_MIN",
    }

    def __init__(self, clang_analyzer: ClangAnalyzer):
        """シンボル解決器を初期化する。

        Args:
            clang_analyzer: ClangAnalyzerインスタンス
        """
        self.analyzer = clang_analyzer
        self._ci = clang_analyzer.ci

    def find_types_in_function(
        self,
        function_code: str,
        file_path: str,
        max_types: int = 10
    ) -> List[TypeDefinition]:
        """関数内で使用されている型定義を検索する。

        Args:
            function_code: 関数のソースコード
            file_path: ソースファイルのパス
            max_types: 返す型の最大数

        Returns:
            TypeDefinitionオブジェクトのリスト
        """
        # コードから型名候補を抽出
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

                # 定義のみを取得
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
        """コードから潜在的な型名を抽出する。

        Args:
            code: 解析するソースコード

        Returns:
            潜在的な型名のセット
        """
        # 型名のパターン:
        # - 大文字で始まり英数字/アンダースコアが続く
        # - 小文字で始まり小文字/数字が続いて_tで終わる
        pattern = r'\b([A-Z][A-Za-z0-9_]*|[a-z][a-z0-9_]*_t)\b'
        matches = re.findall(pattern, code)

        # 標準型を除外
        result = {m for m in matches if m not in self.STD_TYPES}

        return result

    def _cursor_to_type_definition(
        self,
        cursor
    ) -> Optional[TypeDefinition]:
        """カーソルをTypeDefinitionに変換する。

        Args:
            cursor: 型カーソル

        Returns:
            TypeDefinition、エラー時はNone
        """
        try:
            extent = cursor.extent

            if not cursor.location.file:
                return None

            file_path = cursor.location.file.name

            # 型定義コードを読み込む
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            code = "".join(lines[extent.start.line - 1:extent.end.line])

            # カーソル種別を型種別文字列にマッピング
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
        """コード内で使用されているマクロ定義を検索する。

        Args:
            code: 解析するソースコード
            file_path: ソースファイルのパス
            max_macros: 返すマクロの最大数

        Returns:
            MacroDefinitionオブジェクトのリスト
        """
        # マクロ名候補を抽出
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

        # マクロ定義を反復処理
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
        """コードから潜在的なマクロ名を抽出する。

        Args:
            code: 解析するソースコード

        Returns:
            潜在的なマクロ名のセット
        """
        # マクロ名のパターン: 大文字とアンダースコア
        pattern = r'\b([A-Z][A-Z0-9_]+)\b'
        matches = re.findall(pattern, code)

        # 一般的なマクロと短い名前を除外
        result = {
            m for m in matches
            if m not in self.COMMON_MACROS and len(m) > 2
        }

        return result

    def _cursor_to_macro_definition(
        self,
        cursor
    ) -> Optional[MacroDefinition]:
        """カーソルをMacroDefinitionに変換する。

        Args:
            cursor: マクロカーソル

        Returns:
            MacroDefinition、エラー時はNone
        """
        try:
            tokens = list(cursor.get_tokens())
            if not tokens:
                return None

            # トークンから定義を再構築
            definition = " ".join(t.spelling for t in tokens)

            # 関数形式マクロかどうかをチェック
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
        """ファイルがインクルードしている全ヘッダーを検索する。

        Args:
            file_path: ソースファイルのパス

        Returns:
            インクルードされたヘッダーパスのリスト
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
