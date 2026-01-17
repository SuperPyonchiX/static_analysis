"""Retry utilities with exponential backoff."""

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
    """Decorator for retry with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Base delay between retries (seconds)
        max_delay: Maximum delay between retries (seconds)
        exponential_base: Base for exponential backoff
        exceptions: Tuple of exception types to catch
        on_retry: Optional callback called on each retry

    Returns:
        Decorated function
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

                    # Calculate delay with exponential backoff
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
    """Decorator for retrying API calls.

    Handles common OpenAI API errors.

    Args:
        max_retries: Maximum retry attempts
        base_delay: Base delay between retries

    Returns:
        Decorated function
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
    """State tracker for retry operations."""

    def __init__(self, max_retries: int = 3):
        """Initialize retry state.

        Args:
            max_retries: Maximum retry attempts
        """
        self.max_retries = max_retries
        self.attempt = 0
        self.last_error: Optional[Exception] = None

    def should_retry(self) -> bool:
        """Check if should retry.

        Returns:
            True if more retries available
        """
        return self.attempt < self.max_retries

    def record_attempt(self, error: Optional[Exception] = None) -> None:
        """Record an attempt.

        Args:
            error: Error from the attempt (if any)
        """
        self.attempt += 1
        if error:
            self.last_error = error

    def get_delay(self, base_delay: float = 1.0) -> float:
        """Get delay for next retry.

        Args:
            base_delay: Base delay

        Returns:
            Delay in seconds
        """
        return min(base_delay * (2 ** (self.attempt - 1)), 60.0)

    def reset(self) -> None:
        """Reset the retry state."""
        self.attempt = 0
        self.last_error = None
