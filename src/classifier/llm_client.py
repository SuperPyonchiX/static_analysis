"""Azure OpenAI API client for classification."""

from typing import Optional
from dataclasses import dataclass
from enum import Enum
import time
import logging

from openai import AzureOpenAI
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ClassificationTypeEnum(str, Enum):
    """Classification type for JSON output."""
    FALSE_POSITIVE = "FALSE_POSITIVE"
    DEVIATION = "DEVIATION"
    FIX_REQUIRED = "FIX_REQUIRED"
    UNDETERMINED = "UNDETERMINED"


class ClassificationResponse(BaseModel):
    """Structured output model for classification response."""

    classification: ClassificationTypeEnum = Field(
        description="分類結果: FALSE_POSITIVE(誤検知), DEVIATION(逸脱), FIX_REQUIRED(修正), UNDETERMINED(判定不可)"
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="確信度 (0.0-1.0)"
    )
    reason: str = Field(
        description="分類理由の詳細説明（日本語）"
    )
    rule_analysis: str = Field(
        description="該当ルールの観点からの分析（日本語）"
    )
    code_analysis: str = Field(
        description="コードの観点からの分析（日本語）"
    )


@dataclass
class LLMConfig:
    """Configuration for LLM client."""
    azure_endpoint: str
    api_key: str
    api_version: str = "2024-10-21"  # Structured Outputs support
    deployment_name: str = "gpt-5-mini"
    max_tokens: int = 4096
    temperature: float = 0.1  # Low temperature for consistency
    request_delay: float = 1.0  # Delay between requests (seconds)


class LLMError(Exception):
    """Error from LLM API."""
    pass


class LLMClient:
    """Azure OpenAI API client for static analysis classification."""

    def __init__(self, config: LLMConfig):
        """Initialize the LLM client.

        Args:
            config: LLM configuration
        """
        self.config = config
        self.client = AzureOpenAI(
            azure_endpoint=config.azure_endpoint,
            api_key=config.api_key,
            api_version=config.api_version
        )
        self._last_request_time = 0.0

        logger.info(
            f"LLMClient initialized with deployment: {config.deployment_name}"
        )

    def classify(
        self,
        system_prompt: str,
        user_prompt: str,
        max_retries: int = 3
    ) -> Optional[ClassificationResponse]:
        """Classify a static analysis finding.

        Args:
            system_prompt: System prompt defining the classification task
            user_prompt: User prompt with code and finding information
            max_retries: Maximum number of retry attempts

        Returns:
            ClassificationResponse or None on failure
        """
        self._wait_for_rate_limit()

        for attempt in range(max_retries):
            try:
                response = self.client.beta.chat.completions.parse(
                    model=self.config.deployment_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    response_format=ClassificationResponse,
                    max_tokens=self.config.max_tokens,
                    temperature=self.config.temperature
                )

                self._last_request_time = time.time()

                # Get parsed result
                parsed = response.choices[0].message.parsed

                if parsed:
                    logger.debug(
                        f"Classification: {parsed.classification.value} "
                        f"(confidence: {parsed.confidence:.0%})"
                    )
                    return parsed

                logger.warning("Empty response from LLM")
                return None

            except Exception as e:
                logger.warning(
                    f"LLM API attempt {attempt + 1}/{max_retries} failed: {e}"
                )

                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) * self.config.request_delay
                    logger.info(f"Retrying in {wait_time:.1f}s...")
                    time.sleep(wait_time)
                else:
                    raise LLMError(
                        f"LLM API call failed after {max_retries} attempts: {e}"
                    )

        return None

    def classify_batch(
        self,
        system_prompt: str,
        user_prompts: list,
        max_retries: int = 3
    ) -> list:
        """Classify multiple findings sequentially.

        Future enhancement: Can be made async for parallel processing.

        Args:
            system_prompt: System prompt
            user_prompts: List of user prompts
            max_retries: Maximum retry attempts per request

        Returns:
            List of ClassificationResponse or None for each prompt
        """
        results = []

        for i, user_prompt in enumerate(user_prompts):
            logger.info(f"Processing {i + 1}/{len(user_prompts)}")

            try:
                result = self.classify(system_prompt, user_prompt, max_retries)
                results.append(result)
            except LLMError as e:
                logger.error(f"Failed to classify item {i + 1}: {e}")
                results.append(None)

        return results

    def _wait_for_rate_limit(self) -> None:
        """Wait if needed to respect rate limits."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.config.request_delay:
            sleep_time = self.config.request_delay - elapsed
            time.sleep(sleep_time)

    def test_connection(self) -> bool:
        """Test the API connection.

        Returns:
            True if connection is successful
        """
        try:
            response = self.client.chat.completions.create(
                model=self.config.deployment_name,
                messages=[
                    {"role": "user", "content": "Hello"}
                ],
                max_tokens=10
            )
            logger.info("LLM connection test successful")
            return True
        except Exception as e:
            logger.error(f"LLM connection test failed: {e}")
            return False
