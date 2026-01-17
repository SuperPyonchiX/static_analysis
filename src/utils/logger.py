"""ロギング設定モジュール。"""

import logging
import sys
from pathlib import Path
from typing import Optional
from datetime import datetime


def setup_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    format_string: Optional[str] = None
) -> logging.Logger:
    """ロギング設定をセットアップする。

    Args:
        level: ログレベル（DEBUG, INFO, WARNING, ERROR, CRITICAL）
        log_file: ログファイルへのパス（省略可）
        format_string: カスタムフォーマット文字列（省略可）

    Returns:
        ルートロガー
    """
    # デフォルトフォーマット
    if format_string is None:
        format_string = (
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

    # レベル文字列をロギングレベルに変換
    log_level = getattr(logging, level.upper(), logging.INFO)

    # フォーマッターを作成
    formatter = logging.Formatter(format_string)

    # ルートロガーを設定
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # 既存のハンドラーを削除
    root_logger.handlers.clear()

    # コンソールハンドラー
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # ファイルハンドラー（指定された場合）
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(
            log_path,
            encoding="utf-8"
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    return root_logger


def get_log_filename(prefix: str = "static_analysis") -> str:
    """タイムスタンプ付きのログファイル名を生成する。

    Args:
        prefix: ログファイル名のプレフィックス

    Returns:
        タイムスタンプ付きのログファイル名
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{timestamp}.log"


class ProgressLogger:
    """進捗ログ出力用のヘルパークラス。"""

    def __init__(
        self,
        total: int,
        logger: Optional[logging.Logger] = None,
        log_interval: int = 10
    ):
        """進捗ロガーを初期化する。

        Args:
            total: アイテムの総数
            logger: 使用するロガー
            log_interval: 進捗更新の間隔
        """
        self.total = total
        self.current = 0
        self.logger = logger or logging.getLogger(__name__)
        self.log_interval = log_interval

    def update(self, message: Optional[str] = None) -> None:
        """進捗を更新する。

        Args:
            message: 含めるメッセージ（省略可）
        """
        self.current += 1
        progress = self.current / self.total * 100

        if self.current % self.log_interval == 0 or self.current == self.total:
            msg = f"Progress: {self.current}/{self.total} ({progress:.1f}%)"
            if message:
                msg += f" - {message}"
            self.logger.info(msg)

    def complete(self, message: str = "Complete") -> None:
        """進捗を完了としてマークする。

        Args:
            message: 完了メッセージ
        """
        self.logger.info(f"{message}: {self.total} items processed")
