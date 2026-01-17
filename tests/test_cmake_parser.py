"""CMakeLists.txtパーサーのテスト。"""

import json
import pytest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.io.cmake_parser import CMakeParser, CMakeConfig


class TestCMakeConfig:
    """CMakeConfigデータクラスのテスト。"""

    def test_default_values(self):
        """デフォルト値のテスト。"""
        config = CMakeConfig()
        assert config.include_paths == []
        assert config.source_directories == []
        assert config.compiler_args == []
        assert config.cxx_standard is None
        assert config.project_name is None


class TestCMakeParserCompileCommands:
    """compile_commands.jsonを使用したCMakeParserのテスト。"""

    def test_parse_compile_commands_basic(self):
        """基本的なcompile_commands.jsonのパーステスト。"""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            build_dir = project_root / "build"
            build_dir.mkdir()

            # テスト用ソースファイルを作成
            src_dir = project_root / "src"
            src_dir.mkdir()
            (src_dir / "main.cpp").write_text("int main() {}")

            # compile_commands.jsonを作成
            compile_commands = [
                {
                    "directory": str(build_dir),
                    "command": f"g++ -I{project_root}/include -DDEBUG -std=c++14 -c {src_dir}/main.cpp",
                    "file": str(src_dir / "main.cpp")
                }
            ]
            (build_dir / "compile_commands.json").write_text(
                json.dumps(compile_commands)
            )

            # インクルードディレクトリを作成
            include_dir = project_root / "include"
            include_dir.mkdir()

            # パース実行
            parser = CMakeParser(str(project_root))
            config = parser.parse()

            assert str(include_dir.resolve()) in config.include_paths
            assert "-DDEBUG" in config.compiler_args
            assert config.cxx_standard == "c++14"

    def test_parse_compile_commands_with_arguments_list(self):
        """arguments配列形式のcompile_commands.jsonのパーステスト。"""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            build_dir = project_root / "build"
            build_dir.mkdir()

            # テスト用ソースファイルを作成
            src_dir = project_root / "src"
            src_dir.mkdir()
            (src_dir / "main.cpp").write_text("int main() {}")

            # インクルードディレクトリを作成
            include_dir = project_root / "include"
            include_dir.mkdir()

            # arguments配列形式のcompile_commands.jsonを作成
            compile_commands = [
                {
                    "directory": str(build_dir),
                    "arguments": [
                        "g++",
                        f"-I{include_dir}",
                        "-DTEST_DEFINE",
                        "-std=c++17",
                        "-c",
                        str(src_dir / "main.cpp")
                    ],
                    "file": str(src_dir / "main.cpp")
                }
            ]
            (build_dir / "compile_commands.json").write_text(
                json.dumps(compile_commands)
            )

            # パース実行
            parser = CMakeParser(str(project_root))
            config = parser.parse()

            assert str(include_dir.resolve()) in config.include_paths
            assert "-DTEST_DEFINE" in config.compiler_args
            assert config.cxx_standard == "c++17"

    def test_find_compile_commands_in_various_locations(self):
        """様々なビルドディレクトリでのcompile_commands.json検索テスト。"""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # cmake-build-debugディレクトリでテスト
            cmake_build_debug = project_root / "cmake-build-debug"
            cmake_build_debug.mkdir()

            compile_commands = [{"directory": str(cmake_build_debug), "command": "g++ -c test.cpp", "file": "test.cpp"}]
            (cmake_build_debug / "compile_commands.json").write_text(
                json.dumps(compile_commands)
            )

            parser = CMakeParser(str(project_root))
            found = parser._find_compile_commands()

            assert found is not None
            assert "cmake-build-debug" in str(found)


class TestCMakeParserStaticParsing:
    """CMakeLists.txt静的解析のテスト。"""

    def test_parse_cmake_project_name(self):
        """CMakeLists.txtからのプロジェクト名抽出テスト。"""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            cmake_content = """
cmake_minimum_required(VERSION 3.14)
project(MyAwesomeProject)
"""
            (project_root / "CMakeLists.txt").write_text(cmake_content)

            parser = CMakeParser(str(project_root))
            config = parser._parse_cmake_files()

            assert config.project_name == "MyAwesomeProject"

    def test_parse_cmake_cxx_standard(self):
        """CMakeLists.txtからのC++標準抽出テスト。"""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            cmake_content = """
cmake_minimum_required(VERSION 3.14)
project(TestProject)
set(CMAKE_CXX_STANDARD 14)
"""
            (project_root / "CMakeLists.txt").write_text(cmake_content)

            parser = CMakeParser(str(project_root))
            config = parser._parse_cmake_files()

            assert config.cxx_standard == "c++14"
            assert "-std=c++14" in config.compiler_args

    def test_parse_cmake_include_directories(self):
        """CMakeLists.txtからのinclude_directories抽出テスト。"""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # ディレクトリを作成
            include_dir = project_root / "include"
            include_dir.mkdir()
            third_party = project_root / "third_party"
            third_party.mkdir()

            cmake_content = f"""
cmake_minimum_required(VERSION 3.14)
project(TestProject)
include_directories(include third_party)
"""
            (project_root / "CMakeLists.txt").write_text(cmake_content)

            parser = CMakeParser(str(project_root))
            config = parser._parse_cmake_files()

            assert str(include_dir.resolve()) in config.include_paths
            assert str(third_party.resolve()) in config.include_paths

    def test_parse_cmake_target_include_directories(self):
        """CMakeLists.txtからのtarget_include_directories抽出テスト。"""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # ディレクトリを作成
            include_dir = project_root / "include"
            include_dir.mkdir()

            cmake_content = f"""
cmake_minimum_required(VERSION 3.14)
project(TestProject)
add_executable(myapp main.cpp)
target_include_directories(myapp PUBLIC include)
"""
            (project_root / "CMakeLists.txt").write_text(cmake_content)

            parser = CMakeParser(str(project_root))
            config = parser._parse_cmake_files()

            assert str(include_dir.resolve()) in config.include_paths

    def test_parse_cmake_add_subdirectory(self):
        """CMakeLists.txtからのadd_subdirectory抽出テスト。"""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # サブディレクトリを作成
            src_dir = project_root / "src"
            src_dir.mkdir()
            lib_dir = project_root / "lib"
            lib_dir.mkdir()

            cmake_content = """
cmake_minimum_required(VERSION 3.14)
project(TestProject)
add_subdirectory(src)
add_subdirectory(lib)
"""
            (project_root / "CMakeLists.txt").write_text(cmake_content)

            parser = CMakeParser(str(project_root))
            config = parser._parse_cmake_files()

            assert str(src_dir.resolve()) in config.source_directories
            assert str(lib_dir.resolve()) in config.source_directories

    def test_parse_cmake_add_compile_definitions(self):
        """CMakeLists.txtからのadd_compile_definitions抽出テスト。"""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            cmake_content = """
cmake_minimum_required(VERSION 3.14)
project(TestProject)
add_compile_definitions(DEBUG AUTOSAR_AP)
"""
            (project_root / "CMakeLists.txt").write_text(cmake_content)

            parser = CMakeParser(str(project_root))
            config = parser._parse_cmake_files()

            assert "-DDEBUG" in config.compiler_args
            assert "-DAUTOSAR_AP" in config.compiler_args

    def test_parse_cmake_variable_expansion(self):
        """CMAKE変数展開のテスト。"""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # ディレクトリを作成
            include_dir = project_root / "include"
            include_dir.mkdir()

            cmake_content = """
cmake_minimum_required(VERSION 3.14)
project(TestProject)
include_directories(${CMAKE_SOURCE_DIR}/include)
"""
            (project_root / "CMakeLists.txt").write_text(cmake_content)

            parser = CMakeParser(str(project_root))
            config = parser._parse_cmake_files()

            assert str(include_dir.resolve()) in config.include_paths

    def test_parse_cmake_fallback_to_src_directory(self):
        """サブディレクトリ未指定時のsrc/ディレクトリへのフォールバックテスト。"""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # srcディレクトリを作成
            src_dir = project_root / "src"
            src_dir.mkdir()

            cmake_content = """
cmake_minimum_required(VERSION 3.14)
project(TestProject)
"""
            (project_root / "CMakeLists.txt").write_text(cmake_content)

            parser = CMakeParser(str(project_root))
            config = parser._parse_cmake_files()

            assert str(src_dir.resolve()) in config.source_directories

    def test_parse_cmake_no_cmakelists(self):
        """CMakeLists.txt未存在時の処理テスト。"""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            parser = CMakeParser(str(project_root))
            config = parser._parse_cmake_files()

            assert config.include_paths == []
            assert config.source_directories == []
            assert config.compiler_args == []


class TestCMakeParserIntegration:
    """CMakeParserの統合テスト。"""

    def test_parse_prioritizes_compile_commands(self):
        """compile_commands.jsonがCMakeLists.txtより優先されることのテスト。"""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # CMakeLists.txtを作成
            cmake_content = """
cmake_minimum_required(VERSION 3.14)
project(TestProject)
set(CMAKE_CXX_STANDARD 14)
"""
            (project_root / "CMakeLists.txt").write_text(cmake_content)

            # compile_commands.json付きのbuildディレクトリを作成
            build_dir = project_root / "build"
            build_dir.mkdir()

            src_dir = project_root / "src"
            src_dir.mkdir()
            (src_dir / "main.cpp").write_text("int main() {}")

            compile_commands = [
                {
                    "directory": str(build_dir),
                    "command": "g++ -std=c++17 -c " + str(src_dir / "main.cpp"),
                    "file": str(src_dir / "main.cpp")
                }
            ]
            (build_dir / "compile_commands.json").write_text(
                json.dumps(compile_commands)
            )

            parser = CMakeParser(str(project_root))
            config = parser.parse()

            # CMakeLists.txtのC++14ではなく、compile_commands.jsonのC++17が使用されるべき
            assert config.cxx_standard == "c++17"

    def test_full_cmake_project_parsing(self):
        """完全なCMakeプロジェクト構造のパーステスト。"""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # ディレクトリ構造を作成
            (project_root / "include").mkdir()
            (project_root / "src").mkdir()
            (project_root / "lib").mkdir()

            # CMakeLists.txtを作成
            cmake_content = """
cmake_minimum_required(VERSION 3.14)
project(AutomotiveApp)

set(CMAKE_CXX_STANDARD 14)

include_directories(include)
add_compile_definitions(AUTOSAR_AP DEBUG)

add_subdirectory(src)
add_subdirectory(lib)
"""
            (project_root / "CMakeLists.txt").write_text(cmake_content)

            # パース実行
            parser = CMakeParser(str(project_root))
            config = parser.parse()

            assert config.project_name == "AutomotiveApp"
            assert config.cxx_standard == "c++14"
            assert str((project_root / "include").resolve()) in config.include_paths
            assert str((project_root / "src").resolve()) in config.source_directories
            assert str((project_root / "lib").resolve()) in config.source_directories
            assert "-DAUTOSAR_AP" in config.compiler_args
            assert "-DDEBUG" in config.compiler_args
            assert "-std=c++14" in config.compiler_args
