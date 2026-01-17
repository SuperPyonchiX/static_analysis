"""Configuration management."""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from pathlib import Path
import os
import logging

import yaml

logger = logging.getLogger(__name__)


@dataclass
class Config:
    """Application configuration."""

    # Azure OpenAI settings
    azure_endpoint: str = ""
    azure_api_key: str = ""
    azure_api_version: str = "2024-10-21"
    deployment_name: str = "gpt-5-mini"

    # Include paths for C++ parsing
    include_paths: List[str] = field(default_factory=list)

    # Source directories for caller tracking
    source_directories: List[str] = field(default_factory=list)

    # Additional compiler arguments
    compiler_args: List[str] = field(default_factory=list)

    # Processing settings
    confidence_threshold: float = 0.8  # Threshold for Phase 2
    request_delay: float = 1.0  # Delay between API calls (seconds)
    max_input_tokens: int = 250000  # Maximum input tokens

    # Rules source configuration
    rules_source: Dict[str, Any] = field(default_factory=dict)

    # Logging settings
    log_level: str = "INFO"
    log_file: Optional[str] = None

    @classmethod
    def from_yaml(cls, file_path: str) -> "Config":
        """Load configuration from YAML file.

        Args:
            file_path: Path to YAML configuration file

        Returns:
            Config instance
        """
        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        config = cls()

        # Azure settings (environment variables take precedence)
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

        # Path settings
        config.include_paths = data.get("include_paths", [])
        config.source_directories = data.get("source_directories", [])
        config.compiler_args = data.get("compiler_args", [])

        # Processing settings
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

        # Rules source
        config.rules_source = data.get("rules_source", {})

        # Logging
        config.log_level = data.get("log_level", config.log_level)
        config.log_file = data.get("log_file")

        logger.info(f"Configuration loaded from {file_path}")
        return config

    @classmethod
    def from_dict(cls, data: dict) -> "Config":
        """Create configuration from dictionary.

        Args:
            data: Configuration dictionary

        Returns:
            Config instance
        """
        config = cls()

        for key, value in data.items():
            if hasattr(config, key):
                setattr(config, key, value)

        return config

    def validate(self) -> List[str]:
        """Validate configuration.

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        if not self.azure_endpoint:
            errors.append("azure_endpoint is required")
        if not self.azure_api_key:
            errors.append("azure_api_key is required")

        # Validate paths exist
        for path in self.include_paths:
            if not Path(path).exists():
                logger.warning(f"Include path does not exist: {path}")

        for path in self.source_directories:
            if not Path(path).exists():
                errors.append(f"Source directory does not exist: {path}")

        return errors

    def to_dict(self) -> dict:
        """Convert configuration to dictionary.

        Returns:
            Configuration as dictionary
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
        """Get all source files from source directories.

        Returns:
            List of source file paths
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
        # 保存先ディレクトリが存在しない場合は作成
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
