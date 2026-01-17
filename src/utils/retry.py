"""指数バックオフ付きリトライユーティリティ。"""

import time
import functools
from typing import Type, Tuple, Callable, Optional, Any
import logging

logger = logging.getLogger(__name__)


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[Exception, int], None]] = None
):
    """指数バックオフ付きリトライのデコレーター。

    Args:
        max_retries: 最大リトライ回数
        base_delay: リトライ間の基本遅延（秒）
        max_delay: リトライ間の最大遅延（秒）
        exponential_base: 指数バックオフの底
        exceptions: キャッチする例外タイプのタプル
        on_retry: 各リトライ時に呼び出されるコールバック（省略可）

    Returns:
        デコレートされた関数
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt == max_retries:
                        logger.error(
                            f"Max retries ({max_retries}) exceeded for "
                            f"{func.__name__}"
                        )
                        raise

                    # 指数バックオフで遅延を計算
                    delay = min(
                        base_delay * (exponential_base ** attempt),
                        max_delay
                    )

                    logger.warning(
                        f"Attempt {attempt + 1}/{max_retries + 1} failed for "
                        f"{func.__name__}: {e}. Retrying in {delay:.1f}s..."
                    )

                    if on_retry:
                        on_retry(e, attempt)

                    time.sleep(delay)

            raise last_exception

        return wrapper
    return decorator


def retry_api_call(max_retries: int = 3, base_delay: float = 2.0):
    """API呼び出しリトライ用のデコレーター。

    一般的なOpenAI APIエラーを処理する。

    Args:
        max_retries: 最大リトライ回数
        base_delay: リトライ間の基本遅延

    Returns:
        デコレートされた関数
    """
    try:
        from openai import RateLimitError, APIError, APIConnectionError
        api_exceptions = (RateLimitError, APIError, APIConnectionError)
    except ImportError:
        api_exceptions = (Exception,)

    def log_retry(e: Exception, attempt: int) -> None:
        logger.info(f"API retry triggered: {type(e).__name__}")

    return retry_with_backoff(
        max_retries=max_retries,
        base_delay=base_delay,
        max_delay=60.0,
        exceptions=api_exceptions,
        on_retry=log_retry
    )


class RetryState:
    """リトライ操作の状態トラッカー。"""

    def __init__(self, max_retries: int = 3):
        """リトライ状態を初期化する。

        Args:
            max_retries: 最大リトライ回数
        """
        self.max_retries = max_retries
        self.attempt = 0
        self.last_error: Optional[Exception] = None

    def should_retry(self) -> bool:
        """リトライすべきかを確認する。

        Returns:
            さらにリトライ可能な場合はTrue
        """
        return self.attempt < self.max_retries

    def record_attempt(self, error: Optional[Exception] = None) -> None:
        """試行を記録する。

        Args:
            error: 試行中のエラー（もしあれば）
        """
        self.attempt += 1
        if error:
            self.last_error = error

    def get_delay(self, base_delay: float = 1.0) -> float:
        """次のリトライまでの遅延を取得する。

        Args:
            base_delay: 基本遅延

        Returns:
            遅延（秒）
        """
        return min(base_delay * (2 ** (self.attempt - 1)), 60.0)

    def reset(self) -> None:
        """リトライ状態をリセットする。"""
        self.attempt = 0
        self.last_error = None
