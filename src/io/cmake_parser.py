"""CMakeLists.txt parser for auto-generating configuration."""

from dataclasses import dataclass, field
from typing import List, Optional, Dict
from pathlib import Path
import json
import logging
import re

logger = logging.getLogger(__name__)


@dataclass
class CMakeConfig:
    """CMakeLists.txtから抽出した設定。

    Attributes:
        include_paths: インクルードパスのリスト
        source_directories: ソースディレクトリのリスト
        compiler_args: コンパイラ引数のリスト（-D定義、-std=など）
        cxx_standard: C++標準バージョン（c++14, c++17など）
        project_name: プロジェクト名
    """
    include_paths: List[str] = field(default_factory=list)
    source_directories: List[str] = field(default_factory=list)
    compiler_args: List[str] = field(default_factory=list)
    cxx_standard: Optional[str] = None
    project_name: Optional[str] = None


class CMakeParser:
    """CMakeLists.txtパーサー。

    CMakeプロジェクトを解析し、C++解析に必要な設定を抽出する。
    compile_commands.json が存在する場合はそれを優先使用し、
    存在しない場合は CMakeLists.txt を静的解析する。

    Attributes:
        project_root: CMakeプロジェクトのルートディレクトリ
    """

    def __init__(self, project_root: str):
        """Initialize CMakeParser.

        Args:
            project_root: CMakeプロジェクトのルートディレクトリパス
        """
        self.project_root = Path(project_root)
        self._cmake_vars: Dict[str, str] = {}

    def parse(self) -> CMakeConfig:
        """CMakeプロジェクトを解析。

        compile_commands.json があれば優先使用し、
        なければ CMakeLists.txt を静的解析する。

        Returns:
            CMakeConfig: 抽出された設定
        """
        config = CMakeConfig()

        # 1. compile_commands.json があれば優先使用
        compile_commands = self._find_compile_commands()
        if compile_commands:
            logger.info(f"Using compile_commands.json: {compile_commands}")
            config = self._parse_compile_commands(compile_commands)
        else:
            # 2. CMakeLists.txt を静的解析
            logger.info("Parsing CMakeLists.txt statically")
            config = self._parse_cmake_files()

        return config

    def _find_compile_commands(self) -> Optional[Path]:
        """compile_commands.json を検索。

        一般的なビルドディレクトリを探索する。

        Returns:
            compile_commands.json のパス、見つからない場合は None
        """
        candidates = [
            self.project_root / "build" / "compile_commands.json",
            self.project_root / "cmake-build-debug" / "compile_commands.json",
            self.project_root / "cmake-build-release" / "compile_commands.json",
            self.project_root / "out" / "build" / "compile_commands.json",
            self.project_root / "compile_commands.json",
        ]
        for path in candidates:
            if path.exists():
                return path
        return None

    def _parse_compile_commands(self, path: Path) -> CMakeConfig:
        """compile_commands.json をパース。

        Args:
            path: compile_commands.json のパス

        Returns:
            CMakeConfig: 抽出された設定
        """
        config = CMakeConfig()
        include_set: set[str] = set()
        source_dirs: set[str] = set()
        definitions: set[str] = set()
        cxx_standard: Optional[str] = None

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Failed to parse compile_commands.json: {e}")
            return config

        for entry in data:
            command = entry.get("command", "") or entry.get("arguments", [])
            if isinstance(command, list):
                args = command
            else:
                args = command.split()

            i = 0
            while i < len(args):
                arg = args[i]
                if arg.startswith("-I"):
                    # -I/path または -I /path の両方に対応
                    if len(arg) > 2:
                        inc_path = arg[2:]
                    elif i + 1 < len(args):
                        i += 1
                        inc_path = args[i]
                    else:
                        inc_path = ""
                    if inc_path:
                        try:
                            resolved = Path(inc_path).resolve()
                            if resolved.exists():
                                include_set.add(str(resolved))
                        except (OSError, ValueError):
                            pass
                elif arg.startswith("-D"):
                    definitions.add(arg)
                elif arg.startswith("-std=c++"):
                    cxx_standard = arg.split("=")[1]
                i += 1

            # ソースディレクトリを収集
            source_file = entry.get("file", "")
            if source_file:
                try:
                    source_path = Path(source_file).resolve()
                    if source_path.exists():
                        source_dirs.add(str(source_path.parent))
                except (OSError, ValueError):
                    pass

        config.include_paths = sorted(include_set)
        config.source_directories = sorted(source_dirs)
        config.compiler_args = sorted(definitions)
        if cxx_standard:
            config.cxx_standard = cxx_standard
            config.compiler_args.append(f"-std={cxx_standard}")
            config.compiler_args = sorted(set(config.compiler_args))

        logger.info(
            f"Extracted from compile_commands.json: "
            f"{len(config.include_paths)} include paths, "
            f"{len(config.source_directories)} source directories, "
            f"{len(config.compiler_args)} compiler args"
        )

        return config

    def _parse_cmake_files(self) -> CMakeConfig:
        """CMakeLists.txt を静的解析。

        Returns:
            CMakeConfig: 抽出された設定
        """
        config = CMakeConfig()
        cmake_file = self.project_root / "CMakeLists.txt"

        if not cmake_file.exists():
            logger.warning(f"CMakeLists.txt not found at {cmake_file}")
            return config

        try:
            content = cmake_file.read_text(encoding="utf-8", errors="ignore")
        except IOError as e:
            logger.error(f"Failed to read CMakeLists.txt: {e}")
            return config

        # project() からプロジェクト名を抽出
        project_match = re.search(r'project\s*\(\s*(\w+)', content, re.IGNORECASE)
        if project_match:
            config.project_name = project_match.group(1)
            logger.debug(f"Found project name: {config.project_name}")

        # CMAKE_CXX_STANDARD を抽出
        std_match = re.search(
            r'set\s*\(\s*CMAKE_CXX_STANDARD\s+(\d+)\s*\)',
            content,
            re.IGNORECASE
        )
        if std_match:
            config.cxx_standard = f"c++{std_match.group(1)}"
            config.compiler_args.append(f"-std=c++{std_match.group(1)}")
            logger.debug(f"Found C++ standard: {config.cxx_standard}")

        # include_directories() を抽出
        for match in re.finditer(
            r'include_directories\s*\(([^)]+)\)',
            content,
            re.IGNORECASE
        ):
            dirs = self._parse_path_list(match.group(1))
            config.include_paths.extend(dirs)

        # target_include_directories() を抽出
        # 形式: target_include_directories(target PUBLIC|PRIVATE|INTERFACE dir1 dir2 ...)
        for match in re.finditer(
            r'target_include_directories\s*\(\s*\w+\s+(PUBLIC|PRIVATE|INTERFACE)\s+([^)]+)\)',
            content,
            re.IGNORECASE
        ):
            dirs = self._parse_path_list(match.group(2))
            config.include_paths.extend(dirs)

        # add_subdirectory() を抽出
        for match in re.finditer(
            r'add_subdirectory\s*\(\s*([^\s\)]+)',
            content,
            re.IGNORECASE
        ):
            subdir = match.group(1).strip('"\'')
            subdir_path = self.project_root / subdir
            if subdir_path.exists() and subdir_path.is_dir():
                config.source_directories.append(str(subdir_path.resolve()))
                logger.debug(f"Found subdirectory: {subdir_path}")

        # add_compile_definitions() を抽出
        for match in re.finditer(
            r'add_compile_definitions\s*\(([^)]+)\)',
            content,
            re.IGNORECASE
        ):
            defs = self._parse_definition_list(match.group(1))
            config.compiler_args.extend(defs)

        # target_compile_definitions() を抽出
        for match in re.finditer(
            r'target_compile_definitions\s*\(\s*\w+\s+(PUBLIC|PRIVATE|INTERFACE)\s+([^)]+)\)',
            content,
            re.IGNORECASE
        ):
            defs = self._parse_definition_list(match.group(2))
            config.compiler_args.extend(defs)

        # サブディレクトリの CMakeLists.txt も解析
        self._parse_subdirectory_cmake_files(config)

        # ソースディレクトリがない場合は一般的なディレクトリを探す
        if not config.source_directories:
            for common_dir in ["src", "source", "lib"]:
                src_dir = self.project_root / common_dir
                if src_dir.exists() and src_dir.is_dir():
                    config.source_directories.append(str(src_dir.resolve()))
                    break

        # 重複を除去
        config.include_paths = list(dict.fromkeys(config.include_paths))
        config.source_directories = list(dict.fromkeys(config.source_directories))
        config.compiler_args = list(dict.fromkeys(config.compiler_args))

        logger.info(
            f"Extracted from CMakeLists.txt: "
            f"{len(config.include_paths)} include paths, "
            f"{len(config.source_directories)} source directories, "
            f"{len(config.compiler_args)} compiler args"
        )

        return config

    def _parse_subdirectory_cmake_files(self, config: CMakeConfig) -> None:
        """サブディレクトリの CMakeLists.txt を解析。

        Args:
            config: 設定を追加する CMakeConfig オブジェクト
        """
        for subdir in config.source_directories.copy():
            subdir_cmake = Path(subdir) / "CMakeLists.txt"
            if subdir_cmake.exists():
                try:
                    content = subdir_cmake.read_text(encoding="utf-8", errors="ignore")

                    # include_directories() を抽出
                    for match in re.finditer(
                        r'include_directories\s*\(([^)]+)\)',
                        content,
                        re.IGNORECASE
                    ):
                        dirs = self._parse_path_list(
                            match.group(1),
                            base_dir=Path(subdir)
                        )
                        config.include_paths.extend(dirs)

                except IOError as e:
                    logger.warning(f"Failed to read {subdir_cmake}: {e}")

    def _parse_path_list(
        self,
        text: str,
        base_dir: Optional[Path] = None
    ) -> List[str]:
        """パスリストをパース。

        Args:
            text: パスリストを含むテキスト
            base_dir: 相対パスの基準ディレクトリ（省略時は project_root）

        Returns:
            解決されたパスのリスト
        """
        paths: List[str] = []
        base = base_dir or self.project_root

        # 変数展開
        text = re.sub(r'\$\{CMAKE_SOURCE_DIR\}', str(self.project_root), text)
        text = re.sub(r'\$\{CMAKE_CURRENT_SOURCE_DIR\}', str(base), text)
        text = re.sub(r'\$\{PROJECT_SOURCE_DIR\}', str(self.project_root), text)

        for item in re.split(r'\s+', text.strip()):
            item = item.strip('"\'')
            # 未展開の変数やキーワードをスキップ
            if not item or item.startswith('$') or item in ('PUBLIC', 'PRIVATE', 'INTERFACE'):
                continue

            try:
                path = Path(item)
                if not path.is_absolute():
                    path = base / path
                resolved = path.resolve()
                if resolved.exists() and resolved.is_dir():
                    paths.append(str(resolved))
            except (OSError, ValueError) as e:
                logger.debug(f"Failed to resolve path {item}: {e}")

        return paths

    def _parse_definition_list(self, text: str) -> List[str]:
        """定義リストをパース。

        Args:
            text: 定義リストを含むテキスト

        Returns:
            -D形式の定義リスト
        """
        defs: List[str] = []

        for item in re.split(r'\s+', text.strip()):
            item = item.strip('"\'')
            # 未展開の変数やキーワードをスキップ
            if not item or item.startswith('$') or item in ('PUBLIC', 'PRIVATE', 'INTERFACE'):
                continue

            if not item.startswith('-D'):
                item = f"-D{item}"
            defs.append(item)

        return defs
