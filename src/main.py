"""Main entry point for static analysis auto-classifier."""

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
    """Processing statistics."""
    total: int = 0
    phase1_resolved: int = 0
    phase2_resolved: int = 0
    errors: int = 0
    skipped: int = 0


class StaticAnalysisClassifier:
    """Main class for static analysis auto-classification."""

    def __init__(self, config: Config):
        """Initialize the classifier.

        Args:
            config: Application configuration
        """
        self.config = config
        self.stats = ProcessingStats()

        # Initialize components
        self._init_components()

    def _init_components(self) -> None:
        """Initialize all components."""
        # Load rules
        rules_loader = RulesLoader()
        if self.config.rules_source:
            self.rules_db = rules_loader.load(self.config.rules_source)
        else:
            self.rules_db = {}

        # Clang Analyzer
        self.clang_analyzer = ClangAnalyzer(
            include_paths=self.config.include_paths,
            additional_args=self.config.compiler_args
        )

        # Get source files
        source_files = self.config.get_source_files()

        # Context Builder
        self.context_builder = ContextBuilder(
            clang_analyzer=self.clang_analyzer,
            source_files=source_files,
            rules_db=self.rules_db
        )

        # Token Optimizer
        self.token_optimizer = TokenOptimizer(
            max_tokens=self.config.max_input_tokens
        )

        # LLM Client
        llm_config = LLMConfig(
            azure_endpoint=self.config.azure_endpoint,
            api_key=self.config.azure_api_key,
            api_version=self.config.azure_api_version,
            deployment_name=self.config.deployment_name,
            request_delay=self.config.request_delay
        )
        self.llm_client = LLMClient(llm_config)

        # Prompt Builder
        self.prompt_builder = PromptBuilder(rules_db=self.rules_db)

        # Response Parser
        self.response_parser = ResponseParser()

        logger.info("All components initialized")

    def process(
        self,
        input_file: str,
        output_file: str,
        sheet_name: Optional[str] = None
    ) -> None:
        """Process the static analysis report.

        Args:
            input_file: Path to input Excel file
            output_file: Path to output Excel file
            sheet_name: Optional sheet name to process
        """
        logger.info(f"Processing started: {input_file}")

        # Read Excel file
        reader = ExcelReader(input_file, sheet_name=sheet_name)
        findings = reader.read()
        self.stats.total = len(findings)

        logger.info(f"Loaded {self.stats.total} findings")

        # Create finding ID to row number mapping
        finding_id_to_row: Dict[str, int] = {
            f.id: i + 2  # +2 for header row and 1-indexing
            for i, f in enumerate(findings)
        }

        # Process findings
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

        # Write results to Excel
        writer = ExcelWriter(input_file, output_file, sheet_name)
        writer.write_results(results, finding_id_to_row)
        writer.write_summary(list(results.values()))

        # Log statistics
        self._log_statistics()
        logger.info(f"Processing completed: {output_file}")

    def _classify_finding(self, finding: Finding) -> ClassificationResult:
        """Classify a single finding.

        Args:
            finding: Finding to classify

        Returns:
            Classification result
        """
        logger.debug(f"Classifying {finding.id}: {finding.rule_id}")

        # Phase 1: Lightweight classification
        phase1_context = self.context_builder.build_phase1_context(finding)

        if phase1_context is None:
            return self.response_parser.create_skip_result(
                finding.id,
                "コンテキスト抽出失敗",
                1
            )

        # Optimize context
        optimized_context = self.token_optimizer.optimize_context(phase1_context)

        # Build prompts
        system_prompt = self.prompt_builder.build_system_prompt()
        user_prompt = self.prompt_builder.build_phase1_prompt(
            finding, optimized_context
        )

        # Call LLM
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

        # Check if Phase 1 is sufficient
        if result.is_high_confidence(self.config.confidence_threshold):
            logger.debug(
                f"  Phase 1 resolved: {result.classification.value} "
                f"({result.confidence:.0%})"
            )
            return result

        # Phase 2: Additional context
        logger.debug(
            f"  Phase 1 confidence low ({result.confidence:.0%}), "
            "proceeding to Phase 2"
        )

        phase2_context = self.context_builder.build_phase2_context(
            finding, phase1_context
        )
        optimized_context2 = self.token_optimizer.optimize_context(phase2_context)

        # Build Phase 2 prompt
        user_prompt2 = self.prompt_builder.build_phase2_prompt(
            finding, optimized_context2
        )

        # Call LLM again
        try:
            response2 = self.llm_client.classify(system_prompt, user_prompt2)
        except LLMError as e:
            # Return Phase 1 result on Phase 2 failure
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
        """Log processing statistics."""
        logger.info("=" * 50)
        logger.info("Processing Statistics:")
        logger.info(f"  Total findings: {self.stats.total}")
        logger.info(f"  Phase 1 resolved: {self.stats.phase1_resolved}")
        logger.info(f"  Phase 2 resolved: {self.stats.phase2_resolved}")
        logger.info(f"  Errors: {self.stats.errors}")
        logger.info(f"  Skipped: {self.stats.skipped}")
        logger.info("=" * 50)


def main() -> int:
    """Main entry point.

    Returns:
        Exit code
    """
    parser = argparse.ArgumentParser(
        description="Static Analysis Result Auto-Classifier"
    )
    parser.add_argument(
        "-i", "--input",
        required=True,
        help="Input Excel file (CodeSonar report)"
    )
    parser.add_argument(
        "-o", "--output",
        required=True,
        help="Output Excel file"
    )
    parser.add_argument(
        "-c", "--config",
        default="config/default_config.yaml",
        help="Configuration file path"
    )
    parser.add_argument(
        "-s", "--sheet",
        help="Sheet name to process"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args()

    # Load configuration
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"Error: Configuration file not found: {args.config}")
        return 1

    config = Config.from_yaml(str(config_path))

    # Override log level if verbose
    if args.verbose:
        config.log_level = "DEBUG"

    # Set up logging
    setup_logging(level=config.log_level, log_file=config.log_file)

    # Validate configuration
    errors = config.validate()
    if errors:
        for error in errors:
            logger.error(f"Configuration error: {error}")
        return 1

    # Validate input file
    if not Path(args.input).exists():
        logger.error(f"Input file not found: {args.input}")
        return 1

    # Run classification
    try:
        classifier = StaticAnalysisClassifier(config)
        classifier.process(args.input, args.output, args.sheet)
        return 0
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
