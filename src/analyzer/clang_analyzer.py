"""libclangを使用したC++ソースコード解析のラッパー。"""

from typing import List, Optional, Dict
from pathlib import Path
import os
import logging
import threading

logger = logging.getLogger(__name__)


class ClangParseError(Exception):
    """Clangパース時のエラー。"""
    pass


class ClangAnalyzer:
    """libclangを使用したC++解析のメインクラス。

    libclangをラップして高レベルなC++解析機能を提供する。
    TranslationUnitを管理し、パフォーマンス向上のためにキャッシュを提供する。
    """

    def __init__(
        self,
        include_paths: Optional[List[str]] = None,
        additional_args: Optional[List[str]] = None,
        library_path: Optional[str] = None
    ):
        """Clangアナライザーを初期化する。

        Args:
            include_paths: インクルードディレクトリのリスト
            additional_args: 追加のコンパイラ引数
            library_path: libclangライブラリのパス（任意、未指定時は自動検出）
        """
        self._setup_libclang(library_path)

        import clang.cindex as ci
        self._ci = ci

        self.include_paths = include_paths or []
        self.additional_args = additional_args or []
        self.index = ci.Index.create()

        # スレッドセーフなTranslationUnitキャッシュ
        self._translation_units: Dict[str, ci.TranslationUnit] = {}
        self._cache_lock = threading.Lock()

        logger.info(f"ClangAnalyzer initialized with {len(self.include_paths)} include paths")

    def _setup_libclang(self, library_path: Optional[str] = None) -> None:
        """libclangライブラリパスを設定する。

        Args:
            library_path: libclangへの明示的なパス（任意）
        """
        import clang.cindex as ci

        if library_path:
            ci.Config.set_library_path(library_path)
            return

        # pip install libclangでインストールされたライブラリを使用
        # Windowsでは自動的に動作するはず
        try:
            # libclangにアクセス可能かテスト
            ci.Index.create()
            logger.debug("libclang loaded successfully from pip package")
        except Exception as e:
            # 一般的なWindowsパスを試す
            common_paths = [
                r"C:\Program Files\LLVM\bin",
                r"C:\Program Files (x86)\LLVM\bin",
                os.path.expanduser(r"~\AppData\Local\Programs\LLVM\bin"),
            ]

            for path in common_paths:
                dll_path = Path(path) / "libclang.dll"
                if dll_path.exists():
                    ci.Config.set_library_path(path)
                    logger.info(f"Using libclang from: {path}")
                    return

            raise ClangParseError(
                f"Failed to load libclang: {e}. "
                "Please install libclang with 'pip install libclang' or install LLVM."
            )

    def _build_compiler_args(self, file_path: str) -> List[str]:
        """パース用のコンパイラ引数を構築する。

        Args:
            file_path: ソースファイルのパス

        Returns:
            コンパイラ引数のリスト
        """
        args = [
            "-x", "c++",
            "-std=c++14",
            "-D__AUTOSAR_AP__",  # AUTOSAR AP環境マクロ
            "-fparse-all-comments",  # ドキュメント用にコメントをパース
            "-Wno-pragma-once-outside-header",  # pragma警告を抑制
        ]

        # インクルードパスを追加
        for inc_path in self.include_paths:
            args.extend(["-I", inc_path])

        # 追加の引数を追加
        args.extend(self.additional_args)

        return args

    def get_translation_unit(
        self,
        file_path: str,
        skip_function_bodies: bool = True,
        force_reparse: bool = False
    ):
        """ファイルのTranslationUnitを取得する。

        同じファイルの再パースを避けるためにキャッシュを使用する。

        Args:
            file_path: ソースファイルのパス
            skip_function_bodies: 高速パースのため関数本体をスキップ
            force_reparse: キャッシュがあっても強制的に再パース

        Returns:
            clang.cindex.TranslationUnit

        Raises:
            ClangParseError: パースに失敗した場合
        """
        abs_path = os.path.abspath(file_path)
        cache_key = f"{abs_path}:{skip_function_bodies}"

        with self._cache_lock:
            if not force_reparse and cache_key in self._translation_units:
                return self._translation_units[cache_key]

        args = self._build_compiler_args(abs_path)

        # パースオプション
        options = self._ci.TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD
        if skip_function_bodies:
            options |= self._ci.TranslationUnit.PARSE_SKIP_FUNCTION_BODIES

        try:
            tu = self.index.parse(
                abs_path,
                args=args,
                options=options
            )

            # 致命的なエラーをチェック
            if tu is None:
                raise ClangParseError(f"Failed to parse {abs_path}: returned None")

            # 診断情報をログ出力
            for diag in tu.diagnostics:
                if diag.severity >= self._ci.Diagnostic.Error:
                    logger.warning(f"Parse error in {abs_path}: {diag.spelling}")

            with self._cache_lock:
                self._translation_units[cache_key] = tu

            return tu

        except Exception as e:
            raise ClangParseError(f"Failed to parse {abs_path}: {e}")

    def get_translation_unit_full(self, file_path: str):
        """関数本体を含む完全なTranslationUnitを取得する。

        Args:
            file_path: ソースファイルのパス

        Returns:
            関数本体を含むclang.cindex.TranslationUnit
        """
        return self.get_translation_unit(file_path, skip_function_bodies=False)

    def parse_string(self, source_code: str, filename: str = "temp.cpp"):
        """文字列からC++ソースコードをパースする。

        Args:
            source_code: C++ソースコード
            filename: ソースの仮想ファイル名

        Returns:
            clang.cindex.TranslationUnit
        """
        args = self._build_compiler_args(filename)

        try:
            tu = self.index.parse(
                filename,
                args=args,
                unsaved_files=[(filename, source_code)],
                options=self._ci.TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD
            )
            return tu
        except Exception as e:
            raise ClangParseError(f"Failed to parse source string: {e}")

    def clear_cache(self) -> None:
        """TranslationUnitキャッシュをクリアする。"""
        with self._cache_lock:
            self._translation_units.clear()
        logger.debug("TranslationUnit cache cleared")

    def get_cursor_kind(self):
        """外部使用のためのCursorKind列挙を取得する。"""
        return self._ci.CursorKind

    @property
    def ci(self):
        """clang.cindexモジュールを取得する。"""
        return self._ci
