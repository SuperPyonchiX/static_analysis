"""設定管理モジュール。"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from pathlib import Path
import os
import logging

import yaml

logger = logging.getLogger(__name__)


@dataclass
class Config:
    """アプリケーション設定。"""

    # Azure OpenAI設定
    azure_endpoint: str = ""
    azure_api_key: str = ""
    azure_api_version: str = "2024-10-21"
    deployment_name: str = "gpt-5-mini"

    # C++パース用インクルードパス
    include_paths: List[str] = field(default_factory=list)

    # 呼び出し元追跡用ソースディレクトリ
    source_directories: List[str] = field(default_factory=list)

    # 追加のコンパイラ引数
    compiler_args: List[str] = field(default_factory=list)

    # 処理設定
    confidence_threshold: float = 0.8  # Phase 2への閾値
    request_delay: float = 1.0  # API呼び出し間の遅延（秒）
    max_input_tokens: int = 250000  # 最大入力トークン数

    # ルールソース設定
    rules_source: Dict[str, Any] = field(default_factory=dict)

    # ロギング設定
    log_level: str = "INFO"
    log_file: Optional[str] = None

    @classmethod
    def from_yaml(cls, file_path: str) -> "Config":
        """YAMLファイルから設定を読み込む。

        Args:
            file_path: YAML設定ファイルのパス

        Returns:
            Configインスタンス
        """
        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        config = cls()

        # Azure設定（環境変数が優先）
        config.azure_endpoint = os.getenv(
            "AZURE_OPENAI_ENDPOINT",
            data.get("azure_endpoint", "")
        )
        config.azure_api_key = os.getenv(
            "AZURE_OPENAI_API_KEY",
            data.get("azure_api_key", "")
        )
        config.azure_api_version = data.get(
            "azure_api_version",
            config.azure_api_version
        )
        config.deployment_name = data.get(
            "deployment_name",
            config.deployment_name
        )

        # パス設定
        config.include_paths = data.get("include_paths", [])
        config.source_directories = data.get("source_directories", [])
        config.compiler_args = data.get("compiler_args", [])

        # 処理設定
        config.confidence_threshold = data.get(
            "confidence_threshold",
            config.confidence_threshold
        )
        config.request_delay = data.get(
            "request_delay",
            config.request_delay
        )
        config.max_input_tokens = data.get(
            "max_input_tokens",
            config.max_input_tokens
        )

        # ルールソース
        config.rules_source = data.get("rules_source", {})

        # ロギング
        config.log_level = data.get("log_level", config.log_level)
        config.log_file = data.get("log_file")

        logger.info(f"Configuration loaded from {file_path}")
        return config

    @classmethod
    def from_dict(cls, data: dict) -> "Config":
        """辞書から設定を作成する。

        Args:
            data: 設定辞書

        Returns:
            Configインスタンス
        """
        config = cls()

        for key, value in data.items():
            if hasattr(config, key):
                setattr(config, key, value)

        return config

    def validate(self) -> List[str]:
        """設定を検証する。

        Returns:
            検証エラーのリスト（有効な場合は空）
        """
        errors = []

        if not self.azure_endpoint:
            errors.append("azure_endpointは必須です")
        if not self.azure_api_key:
            errors.append("azure_api_keyは必須です")

        # パスの存在を検証
        for path in self.include_paths:
            if not Path(path).exists():
                logger.warning(f"Include path does not exist: {path}")

        for path in self.source_directories:
            if not Path(path).exists():
                errors.append(f"ソースディレクトリが存在しません: {path}")

        return errors

    def to_dict(self) -> dict:
        """設定を辞書に変換する。

        Returns:
            辞書形式の設定
        """
        return {
            "azure_endpoint": self.azure_endpoint,
            "azure_api_version": self.azure_api_version,
            "deployment_name": self.deployment_name,
            "include_paths": self.include_paths,
            "source_directories": self.source_directories,
            "compiler_args": self.compiler_args,
            "confidence_threshold": self.confidence_threshold,
            "request_delay": self.request_delay,
            "max_input_tokens": self.max_input_tokens,
            "rules_source": self.rules_source,
            "log_level": self.log_level,
            "log_file": self.log_file,
        }

    def get_source_files(self) -> List[str]:
        """ソースディレクトリから全ソースファイルを取得する。

        Returns:
            ソースファイルパスのリスト
        """
        source_files = []

        for source_dir in self.source_directories:
            path = Path(source_dir)
            if path.exists():
                source_files.extend(str(f) for f in path.rglob("*.cpp"))
                source_files.extend(str(f) for f in path.rglob("*.cc"))
                source_files.extend(str(f) for f in path.rglob("*.cxx"))
                source_files.extend(str(f) for f in path.rglob("*.c"))

        logger.debug(f"Found {len(source_files)} source files")
        return source_files

    @classmethod
    def from_cmake_project(
        cls,
        project_root: str,
        output_path: Optional[str] = None
    ) -> "Config":
        """CMakeプロジェクトから設定を自動生成。

        CMakeLists.txt または compile_commands.json を解析して、
        C++解析に必要な設定（インクルードパス、ソースディレクトリ、
        コンパイラフラグ）を抽出する。

        Args:
            project_root: CMakeプロジェクトのルートディレクトリ
            output_path: 生成した設定を保存するパス（省略時は保存しない）

        Returns:
            Config: 自動生成された設定
        """
        from .io.cmake_parser import CMakeParser

        parser = CMakeParser(project_root)
        cmake_config = parser.parse()

        config = cls()
        config.include_paths = cmake_config.include_paths
        config.source_directories = cmake_config.source_directories
        config.compiler_args = cmake_config.compiler_args

        if output_path:
            config.save_yaml(output_path)
            logger.info(f"Configuration saved to {output_path}")

        return config

    def save_yaml(self, file_path: str) -> None:
        """設定をYAMLファイルに保存。

        Args:
            file_path: 保存先パス
        """
        # 出力先ディレクトリが存在しない場合は作成
        output_path = Path(file_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        data: Dict[str, Any] = {
            "azure_api_version": self.azure_api_version,
            "deployment_name": self.deployment_name,
            "include_paths": self.include_paths,
            "source_directories": self.source_directories,
            "compiler_args": self.compiler_args,
            "confidence_threshold": self.confidence_threshold,
            "request_delay": self.request_delay,
            "max_input_tokens": self.max_input_tokens,
            "rules_source": self.rules_source,
            "log_level": self.log_level,
        }
        if self.log_file:
            data["log_file"] = self.log_file

        with open(file_path, "w", encoding="utf-8") as f:
            yaml.dump(
                data,
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False
            )

        logger.info(f"Configuration saved to {file_path}")
