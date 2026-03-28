"""promptlint — Analyze LLM prompts for instruction count, redundancy, contradictions, and complexity."""

from __future__ import annotations

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


class PromptAnalyzer:
    """Main entry point for prompt analysis. Loads models once and runs the full pipeline."""

    def __init__(self, **kwargs):
        self.config = Config(**{k: v for k, v in kwargs.items() if hasattr(Config, k)})
        self._load_models()

    def _load_models(self) -> None:
        # Load DeBERTa once, share between classifier and contradiction detector
        self._nli_tokenizer = AutoTokenizer.from_pretrained(self.config.classifier_model)
        self._nli_model = AutoModelForSequenceClassification.from_pretrained(self.config.classifier_model)
        self._nli_model.to(self.config.device)
        self._nli_model.eval()

        self.classifier = InstructionClassifier(self.config, self._nli_model, self._nli_tokenizer)
        self.embedder = InstructionEmbedder(self.config)
        self.redundancy_detector = RedundancyDetector(self.config)
        self.contradiction_detector = ContradictionDetector(self.config, self._nli_model, self._nli_tokenizer)

    def analyze(
        self,
        text: str | None = None,
        system_prompt: str | None = None,
        skills: list[str] | None = None,
        constitution: str | None = None,
        tools: list[dict] | None = None,
        user_message: str | None = None,
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

        # Stage 2: Classify
        classified = self.classifier.classify(chunks)
        instructions = [c for c in classified if c.label == "instruction"]
        non_instructions = [c for c in classified if c.label == "non_instruction"]

        if not instructions:
            return score(instructions, non_instructions, [], [], classified, original_text, self.config)

        # Stage 3: Embed
        embeddings = self.embedder.embed(instructions)

        # Stage 4: Redundancy detection
        redundancy_groups = self.redundancy_detector.detect(instructions, embeddings)

        # Stage 5: Contradiction detection
        contradictions = self.contradiction_detector.detect(instructions, embeddings, redundancy_groups)

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
