"""静的解析自動分類ツールのメインエントリーポイント。"""

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass
import logging

from .config import Config
from .io.excel_reader import ExcelReader
from .io.excel_writer import ExcelWriter
from .io.rules_loader import RulesLoader
from .analyzer.clang_analyzer import ClangAnalyzer
from .context.context_builder import ContextBuilder
from .context.token_optimizer import TokenOptimizer
from .classifier.llm_client import LLMClient, LLMConfig, LLMError
from .classifier.prompt_builder import PromptBuilder
from .classifier.response_parser import ResponseParser
from .models.finding import Finding
from .models.classification import ClassificationResult
from .utils.logger import setup_logging, ProgressLogger

logger = logging.getLogger(__name__)


@dataclass
class ProcessingStats:
    """処理統計情報。"""
    total: int = 0
    phase1_resolved: int = 0
    phase2_resolved: int = 0
    errors: int = 0
    skipped: int = 0


class StaticAnalysisClassifier:
    """静的解析自動分類のメインクラス。"""

    def __init__(self, config: Config):
        """分類器を初期化する。

        Args:
            config: アプリケーション設定
        """
        self.config = config
        self.stats = ProcessingStats()

        # コンポーネントを初期化
        self._init_components()

    def _init_components(self) -> None:
        """すべてのコンポーネントを初期化する。"""
        # ルールを読み込み
        rules_loader = RulesLoader()
        if self.config.rules_source:
            self.rules_db = rules_loader.load(self.config.rules_source)
        else:
            self.rules_db = {}

        # Clang解析器
        self.clang_analyzer = ClangAnalyzer(
            include_paths=self.config.include_paths,
            additional_args=self.config.compiler_args
        )

        # ソースファイルを取得
        source_files = self.config.get_source_files()

        # コンテキストビルダー
        self.context_builder = ContextBuilder(
            clang_analyzer=self.clang_analyzer,
            source_files=source_files,
            rules_db=self.rules_db
        )

        # トークン最適化器
        self.token_optimizer = TokenOptimizer(
            max_tokens=self.config.max_input_tokens
        )

        # LLMクライアント
        llm_config = LLMConfig(
            azure_endpoint=self.config.azure_endpoint,
            api_key=self.config.azure_api_key,
            api_version=self.config.azure_api_version,
            deployment_name=self.config.deployment_name,
            request_delay=self.config.request_delay
        )
        self.llm_client = LLMClient(llm_config)

        # プロンプトビルダー
        self.prompt_builder = PromptBuilder(rules_db=self.rules_db)

        # レスポンスパーサー
        self.response_parser = ResponseParser()

        logger.info("All components initialized")

    def process(
        self,
        input_file: str,
        output_file: str,
        sheet_name: Optional[str] = None
    ) -> None:
        """静的解析レポートを処理する。

        Args:
            input_file: 入力Excelファイルへのパス
            output_file: 出力Excelファイルへのパス
            sheet_name: 処理するシート名（省略可）
        """
        logger.info(f"Processing started: {input_file}")

        # Excelファイルを読み込み
        reader = ExcelReader(input_file, sheet_name=sheet_name)
        findings = reader.read()
        self.stats.total = len(findings)

        logger.info(f"Loaded {self.stats.total} findings")

        # 指摘IDから行番号へのマッピングを作成
        finding_id_to_row: Dict[str, int] = {
            f.id: i + 2  # ヘッダー行と1始まりインデックスのため+2
            for i, f in enumerate(findings)
        }

        # 指摘を処理
        results: Dict[str, ClassificationResult] = {}
        progress = ProgressLogger(self.stats.total, logger, log_interval=10)

        for finding in findings:
            try:
                result = self._classify_finding(finding)
                results[finding.id] = result

                if result.phase == 1:
                    self.stats.phase1_resolved += 1
                else:
                    self.stats.phase2_resolved += 1

            except Exception as e:
                logger.error(f"Error processing {finding.id}: {e}")
                results[finding.id] = self.response_parser.create_error_result(
                    finding.id, str(e), 0
                )
                self.stats.errors += 1

            progress.update(finding.id)

        # 結果をExcelに書き込み
        writer = ExcelWriter(input_file, output_file, sheet_name)
        writer.write_results(results, finding_id_to_row)
        writer.write_summary(list(results.values()))

        # 統計をログ出力
        self._log_statistics()
        logger.info(f"Processing completed: {output_file}")

    def _classify_finding(self, finding: Finding) -> ClassificationResult:
        """単一の指摘を分類する。

        Args:
            finding: 分類する指摘

        Returns:
            分類結果
        """
        logger.debug(f"Classifying {finding.id}: {finding.rule_id}")

        # Phase 1: 軽量分類
        phase1_context = self.context_builder.build_phase1_context(finding)

        if phase1_context is None:
            return self.response_parser.create_skip_result(
                finding.id,
                "コンテキスト抽出失敗",
                1
            )

        # コンテキストを最適化
        optimized_context = self.token_optimizer.optimize_context(phase1_context)

        # プロンプトを構築
        system_prompt = self.prompt_builder.build_system_prompt()
        user_prompt = self.prompt_builder.build_phase1_prompt(
            finding, optimized_context
        )

        # LLMを呼び出し
        try:
            response = self.llm_client.classify(system_prompt, user_prompt)
        except LLMError as e:
            return self.response_parser.create_error_result(
                finding.id, str(e), 1
            )

        if response is None:
            return self.response_parser.create_error_result(
                finding.id, "LLM応答なし", 1
            )

        result = self.response_parser.parse(response, finding.id, phase=1)

        # Phase 1で十分かを確認
        if result.is_high_confidence(self.config.confidence_threshold):
            logger.debug(
                f"  Phase 1 resolved: {result.classification.value} "
                f"({result.confidence:.0%})"
            )
            return result

        # Phase 2: 追加コンテキスト
        logger.debug(
            f"  Phase 1 confidence low ({result.confidence:.0%}), "
            "proceeding to Phase 2"
        )

        phase2_context = self.context_builder.build_phase2_context(
            finding, phase1_context
        )
        optimized_context2 = self.token_optimizer.optimize_context(phase2_context)

        # Phase 2プロンプトを構築
        user_prompt2 = self.prompt_builder.build_phase2_prompt(
            finding, optimized_context2
        )

        # 再度LLMを呼び出し
        try:
            response2 = self.llm_client.classify(system_prompt, user_prompt2)
        except LLMError as e:
            # Phase 2失敗時はPhase 1結果を返す
            result.phase = 2
            return result

        if response2 is None:
            result.phase = 2
            return result

        result2 = self.response_parser.parse(response2, finding.id, phase=2)

        logger.debug(
            f"  Phase 2 resolved: {result2.classification.value} "
            f"({result2.confidence:.0%})"
        )

        return result2

    def _log_statistics(self) -> None:
        """処理統計をログ出力する。"""
        logger.info("=" * 50)
        logger.info("Processing Statistics:")
        logger.info(f"  Total findings: {self.stats.total}")
        logger.info(f"  Phase 1 resolved: {self.stats.phase1_resolved}")
        logger.info(f"  Phase 2 resolved: {self.stats.phase2_resolved}")
        logger.info(f"  Errors: {self.stats.errors}")
        logger.info(f"  Skipped: {self.stats.skipped}")
        logger.info("=" * 50)


def main() -> int:
    """メインエントリーポイント。

    Returns:
        終了コード
    """
    parser = argparse.ArgumentParser(
        description="静的解析結果自動分類ツール"
    )
    parser.add_argument(
        "-i", "--input",
        help="入力Excelファイル（CodeSonarレポート）"
    )
    parser.add_argument(
        "-o", "--output",
        help="出力Excelファイル"
    )
    parser.add_argument(
        "-c", "--config",
        default="config/default_config.yaml",
        help="設定ファイルパス"
    )
    parser.add_argument(
        "-s", "--sheet",
        help="処理するシート名"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="詳細ログを有効にする"
    )
    parser.add_argument(
        "--init-config",
        metavar="PROJECT_DIR",
        help="CMakeプロジェクトから設定ファイルを自動生成"
    )

    args = parser.parse_args()

    # --init-configモードを処理
    if args.init_config:
        return _init_config_from_cmake(args.init_config, args.config, args.verbose)

    # 通常モードでは入力と出力が必要
    if not args.input or not args.output:
        parser.error("分類モードでは--inputと--outputが必要です")

    # 設定を読み込み
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"Error: 設定ファイルが見つかりません: {args.config}")
        return 1

    config = Config.from_yaml(str(config_path))

    # 詳細ログが指定された場合はログレベルを上書き
    if args.verbose:
        config.log_level = "DEBUG"

    # ロギングをセットアップ
    setup_logging(level=config.log_level, log_file=config.log_file)

    # 設定を検証
    errors = config.validate()
    if errors:
        for error in errors:
            logger.error(f"Configuration error: {error}")
        return 1

    # 入力ファイルを検証
    if not Path(args.input).exists():
        logger.error(f"入力ファイルが見つかりません: {args.input}")
        return 1

    # 分類を実行
    try:
        classifier = StaticAnalysisClassifier(config)
        classifier.process(args.input, args.output, args.sheet)
        return 0
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        return 1


def _init_config_from_cmake(
    project_dir: str,
    output_config: str,
    verbose: bool
) -> int:
    """CMakeプロジェクトから設定ファイルを生成する。

    Args:
        project_dir: CMakeプロジェクトのルートディレクトリ
        output_config: 出力設定ファイルパス
        verbose: 詳細ログを有効にするかどうか

    Returns:
        終了コード
    """
    # 初期化モード用のロギングをセットアップ
    log_level = "DEBUG" if verbose else "INFO"
    setup_logging(level=log_level)

    project_path = Path(project_dir)
    if not project_path.exists():
        print(f"Error: プロジェクトディレクトリが見つかりません: {project_dir}")
        return 1

    if not project_path.is_dir():
        print(f"Error: ディレクトリではありません: {project_dir}")
        return 1

    # CMakeLists.txtまたはcompile_commands.jsonを確認
    cmake_file = project_path / "CMakeLists.txt"
    has_cmake = cmake_file.exists()
    has_compile_commands = any([
        (project_path / "build" / "compile_commands.json").exists(),
        (project_path / "cmake-build-debug" / "compile_commands.json").exists(),
        (project_path / "cmake-build-release" / "compile_commands.json").exists(),
        (project_path / "compile_commands.json").exists(),
    ])

    if not has_cmake and not has_compile_commands:
        print(
            f"Error: CMakeLists.txtまたはcompile_commands.jsonが見つかりません: "
            f"{project_dir}"
        )
        return 1

    try:
        config = Config.from_cmake_project(
            str(project_path),
            output_path=output_config
        )

        print(f"設定ファイルを生成しました: {output_config}")
        print(f"  インクルードパス: {len(config.include_paths)}")
        print(f"  ソースディレクトリ: {len(config.source_directories)}")
        print(f"  コンパイラ引数: {len(config.compiler_args)}")

        if config.include_paths:
            print("\nインクルードパス:")
            for path in config.include_paths[:5]:  # 最初の5件を表示
                print(f"  - {path}")
            if len(config.include_paths) > 5:
                print(f"  ... 他 {len(config.include_paths) - 5} 件")

        if config.source_directories:
            print("\nソースディレクトリ:")
            for path in config.source_directories[:5]:  # 最初の5件を表示
                print(f"  - {path}")
            if len(config.source_directories) > 5:
                print(f"  ... 他 {len(config.source_directories) - 5} 件")

        return 0

    except Exception as e:
        print(f"Error: 設定生成中にエラーが発生しました: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
