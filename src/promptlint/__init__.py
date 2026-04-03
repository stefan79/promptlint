"""promptlint — Analyze LLM prompts for instruction count, redundancy, contradictions, and complexity."""

from __future__ import annotations

import logging
import time
from typing import Any

from transformers import AutoModelForSequenceClassification, AutoTokenizer

from promptlint.classifier import InstructionClassifier
from promptlint.config import Config
from promptlint.contradiction import ContradictionDetector
from promptlint.embedder import InstructionEmbedder
from promptlint.models import AnalysisResult, PromptLintError
from promptlint.prompt_parser import parse_files, parse_raw, parse_structured
from promptlint.redundancy import RedundancyDetector
from promptlint.scorer import score

__all__ = ["AnalysisResult", "Config", "PromptAnalyzer", "PromptLintError"]

logger = logging.getLogger("promptlint.pipeline")


class PromptAnalyzer:
    """Main entry point for prompt analysis. Loads models once and runs the full pipeline."""

    def __init__(self, **kwargs: Any) -> None:
        self.config = Config(**{k: v for k, v in kwargs.items() if hasattr(Config, k)})
        self._load_models()

    def _load_models(self) -> None:
        # Classifier: 2-class zero-shot model (entailment / not_entailment)
        cls_tokenizer = AutoTokenizer.from_pretrained(self.config.classifier_model)
        cls_model = AutoModelForSequenceClassification.from_pretrained(self.config.classifier_model)
        cls_model.to(self.config.device)
        cls_model.eval()

        # Contradiction: 3-class NLI cross-encoder (contradiction / entailment / neutral)
        con_tokenizer = AutoTokenizer.from_pretrained(self.config.contradiction_model)
        con_model = AutoModelForSequenceClassification.from_pretrained(self.config.contradiction_model)
        con_model.to(self.config.device)
        con_model.eval()

        self.classifier = InstructionClassifier(self.config, cls_model, cls_tokenizer)  # type: ignore[arg-type]
        self.embedder = InstructionEmbedder(self.config)
        self.redundancy_detector = RedundancyDetector(self.config)
        self.contradiction_detector = ContradictionDetector(self.config, con_model, con_tokenizer)  # type: ignore[arg-type]

    def analyze(
        self,
        text: str | None = None,
        system_prompt: str | None = None,
        skills: list[str] | None = None,
        constitution: str | None = None,
        tools: list[dict] | None = None,
        user_message: str | None = None,
        skip_contradictions: bool = False,
    ) -> AnalysisResult:
        """Run the full analysis pipeline on a prompt."""
        # Parse input into chunks
        if text is not None:
            chunks = parse_raw(text, config=self.config)
            original_text = text
        else:
            chunks = parse_structured(
                system_prompt=system_prompt,
                skills=skills,
                constitution=constitution,
                tools=tools,
                user_message=user_message,
                config=self.config,
            )
            # Reconstruct original text for token counting
            parts = [p for p in [system_prompt] + (skills or []) + [constitution, user_message] if p]
            original_text = "\n\n".join(parts)

        if not chunks:
            return AnalysisResult()

        logger.info("  [chunker]        %d chunks from input", len(chunks))

        # Stage 2: Classify
        logger.info("  [classifier]     classifying %d chunks (this may take a while on CPU)...", len(chunks))
        t0 = time.monotonic()
        classified = self.classifier.classify(chunks)
        instructions = [c for c in classified if c.label == "instruction"]
        non_instructions = [c for c in classified if c.label == "non_instruction"]
        logger.info(
            "  [classifier]     %d instructions, %d non-instructions (%.0fms)",
            len(instructions),
            len(non_instructions),
            (time.monotonic() - t0) * 1000,
        )

        if not instructions:
            return score(instructions, non_instructions, [], [], classified, original_text, self.config)

        # Stage 3: Embed
        t0 = time.monotonic()
        embeddings = self.embedder.embed(instructions)
        logger.info("  [embedder]       %d embeddings (%.0fms)", len(instructions), (time.monotonic() - t0) * 1000)

        # Stage 4: Redundancy detection
        t0 = time.monotonic()
        redundancy_groups = self.redundancy_detector.detect(instructions, embeddings)
        logger.info(
            "  [redundancy]     %d groups found (%.0fms)", len(redundancy_groups), (time.monotonic() - t0) * 1000
        )

        # Stage 5: Contradiction detection
        if skip_contradictions:
            contradictions = []
            logger.info("  [contradiction]  SKIPPED")
        else:
            t0 = time.monotonic()
            contradictions = self.contradiction_detector.detect(instructions, embeddings, redundancy_groups)
            logger.info("  [contradiction]  %d found (%.0fms)", len(contradictions), (time.monotonic() - t0) * 1000)

        # Stage 6: Score
        return score(
            instructions, non_instructions, redundancy_groups, contradictions, classified, original_text, self.config
        )

    def analyze_files(
        self,
        claude_md: str | None = None,
        skill_dirs: list[str] | None = None,
        system_prompt: str | None = None,
    ) -> AnalysisResult:
        """Run analysis on prompt files from disk."""
        chunks = parse_files(
            claude_md=claude_md, skill_dirs=skill_dirs, system_prompt=system_prompt, config=self.config
        )
        # Read original text for token counting
        from pathlib import Path

        parts = []
        if claude_md:
            parts.append(Path(claude_md).read_text())
        if system_prompt:
            parts.append(Path(system_prompt).read_text())
        original_text = "\n\n".join(parts) if parts else ""

        if not chunks:
            return AnalysisResult()

        classified = self.classifier.classify(chunks)
        instructions = [c for c in classified if c.label == "instruction"]
        non_instructions = [c for c in classified if c.label == "non_instruction"]

        if not instructions:
            return score(instructions, non_instructions, [], [], classified, original_text, self.config)

        embeddings = self.embedder.embed(instructions)
        redundancy_groups = self.redundancy_detector.detect(instructions, embeddings)
        contradictions = self.contradiction_detector.detect(instructions, embeddings, redundancy_groups)

        return score(
            instructions, non_instructions, redundancy_groups, contradictions, classified, original_text, self.config
        )
