"""libclang wrapper for C++ source code analysis."""

from typing import List, Optional, Dict
from pathlib import Path
import os
import logging
import threading

logger = logging.getLogger(__name__)


class ClangParseError(Exception):
    """Error during Clang parsing."""
    pass


class ClangAnalyzer:
    """Main class for C++ analysis using libclang.

    This class wraps libclang to provide high-level C++ analysis capabilities.
    It manages TranslationUnits and provides caching for performance.
    """

    def __init__(
        self,
        include_paths: Optional[List[str]] = None,
        additional_args: Optional[List[str]] = None,
        library_path: Optional[str] = None
    ):
        """Initialize the Clang analyzer.

        Args:
            include_paths: List of include directories
            additional_args: Additional compiler arguments
            library_path: Path to libclang library (optional, auto-detected if not provided)
        """
        self._setup_libclang(library_path)

        import clang.cindex as ci
        self._ci = ci

        self.include_paths = include_paths or []
        self.additional_args = additional_args or []
        self.index = ci.Index.create()

        # Thread-safe cache for TranslationUnits
        self._translation_units: Dict[str, ci.TranslationUnit] = {}
        self._cache_lock = threading.Lock()

        logger.info(f"ClangAnalyzer initialized with {len(self.include_paths)} include paths")

    def _setup_libclang(self, library_path: Optional[str] = None) -> None:
        """Set up libclang library path.

        Args:
            library_path: Optional explicit path to libclang
        """
        import clang.cindex as ci

        if library_path:
            ci.Config.set_library_path(library_path)
            return

        # Try to use the library from pip install libclang
        # This should work automatically on Windows
        try:
            # Test if libclang is accessible
            ci.Index.create()
            logger.debug("libclang loaded successfully from pip package")
        except Exception as e:
            # Try common Windows paths
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
        """Build compiler arguments for parsing.

        Args:
            file_path: Path to the source file

        Returns:
            List of compiler arguments
        """
        args = [
            "-x", "c++",
            "-std=c++14",
            "-D__AUTOSAR_AP__",  # AUTOSAR AP environment macro
            "-fparse-all-comments",  # Parse comments for documentation
            "-Wno-pragma-once-outside-header",  # Suppress pragma warnings
        ]

        # Add include paths
        for inc_path in self.include_paths:
            args.extend(["-I", inc_path])

        # Add additional arguments
        args.extend(self.additional_args)

        return args

    def get_translation_unit(
        self,
        file_path: str,
        skip_function_bodies: bool = True,
        force_reparse: bool = False
    ):
        """Get a TranslationUnit for a file.

        Uses caching to avoid re-parsing the same file.

        Args:
            file_path: Path to the source file
            skip_function_bodies: Skip function bodies for faster parsing
            force_reparse: Force re-parsing even if cached

        Returns:
            clang.cindex.TranslationUnit

        Raises:
            ClangParseError: If parsing fails
        """
        abs_path = os.path.abspath(file_path)
        cache_key = f"{abs_path}:{skip_function_bodies}"

        with self._cache_lock:
            if not force_reparse and cache_key in self._translation_units:
                return self._translation_units[cache_key]

        args = self._build_compiler_args(abs_path)

        # Parse options
        options = self._ci.TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD
        if skip_function_bodies:
            options |= self._ci.TranslationUnit.PARSE_SKIP_FUNCTION_BODIES

        try:
            tu = self.index.parse(
                abs_path,
                args=args,
                options=options
            )

            # Check for fatal errors
            if tu is None:
                raise ClangParseError(f"Failed to parse {abs_path}: returned None")

            # Log diagnostics
            for diag in tu.diagnostics:
                if diag.severity >= self._ci.Diagnostic.Error:
                    logger.warning(f"Parse error in {abs_path}: {diag.spelling}")

            with self._cache_lock:
                self._translation_units[cache_key] = tu

            return tu

        except Exception as e:
            raise ClangParseError(f"Failed to parse {abs_path}: {e}")

    def get_translation_unit_full(self, file_path: str):
        """Get a TranslationUnit with full function body parsing.

        Args:
            file_path: Path to the source file

        Returns:
            clang.cindex.TranslationUnit with function bodies
        """
        return self.get_translation_unit(file_path, skip_function_bodies=False)

    def parse_string(self, source_code: str, filename: str = "temp.cpp"):
        """Parse C++ source code from a string.

        Args:
            source_code: C++ source code
            filename: Virtual filename for the source

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
        """Clear the TranslationUnit cache."""
        with self._cache_lock:
            self._translation_units.clear()
        logger.debug("TranslationUnit cache cleared")

    def get_cursor_kind(self):
        """Get the CursorKind enum for external use."""
        return self._ci.CursorKind

    @property
    def ci(self):
        """Get the clang.cindex module."""
        return self._ci
